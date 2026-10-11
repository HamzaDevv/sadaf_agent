"""Typed M2 task protocol and durable local orchestration.

The protocol describes operations only; it intentionally defines no wire format
or endpoint. The bundled client is a deterministic fake for offline development.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
import hashlib
import json
import re
import sqlite3
import time
from typing import Mapping, Protocol, Sequence


class TaskError(RuntimeError):
    pass


class TaskState(StrEnum):
    QUEUED = 'queued'
    RUNNING = 'running'
    AWAITING_INPUT = 'awaiting_input'
    SUCCEEDED = 'succeeded'
    FAILED = 'failed'
    CANCEL_REQUESTED = 'cancel_requested'
    CANCELLED = 'cancelled'
    BLOCKED = 'blocked'


TERMINAL = {TaskState.SUCCEEDED, TaskState.FAILED, TaskState.CANCELLED, TaskState.BLOCKED}


def _identity(value: str, label: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}', value):
        raise ValueError(f'Invalid {label}')
    return value


@dataclass(frozen=True)
class PolicyRevision:
    source_id: str
    document: str
    revision: str

    def __post_init__(self):
        _identity(self.source_id, 'policy source')
        if not self.document or '/' in self.document or '\\' in self.document:
            raise ValueError('Invalid policy document')
        if not self.revision:
            raise ValueError('Policy revision is required')


@dataclass(frozen=True)
class TaskRequest:
    task_id: str
    user_id: str
    project_id: str
    thread_id: str
    outcome: str
    scope: str
    repository: str
    worktree: str | None
    dependencies: tuple[str, ...]
    policies: tuple[PolicyRevision, ...]
    relevant_decisions: tuple[str, ...]
    acceptance_criteria: tuple[str, ...]
    allowed_actions: tuple[str, ...]
    result_requirements: tuple[str, ...]
    idempotency_key: str
    same_checkout: bool = True
    permitted_context: tuple[str, ...] = ()

    def __post_init__(self):
        for key in ('task_id', 'user_id', 'project_id', 'thread_id', 'idempotency_key'):
            _identity(getattr(self, key), key)
        for name in ('outcome', 'scope', 'repository'):
            if not getattr(self, name).strip():
                raise ValueError(f'{name} is required')
        for group_name in ('dependencies', 'relevant_decisions', 'acceptance_criteria',
                           'allowed_actions', 'result_requirements', 'permitted_context'):
            values = getattr(self, group_name)
            if any(not isinstance(value, str) or not value.strip() for value in values):
                raise ValueError(f'{group_name} entries must be non-empty')
        if len(set(self.dependencies)) != len(self.dependencies) or self.task_id in self.dependencies:
            raise ValueError('Dependencies must be unique and cannot include this task')
        if not self.acceptance_criteria or not self.allowed_actions or not self.result_requirements:
            raise ValueError('Acceptance criteria, allowed actions, and result requirements are required')
        if len(set(self.policies)) != len(self.policies):
            raise ValueError('Policy revisions must be unique')


@dataclass(frozen=True)
class TaskResult:
    summary: str
    artifacts: tuple[str, ...] = ()
    validation_evidence: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    complete: bool = True


@dataclass(frozen=True)
class RemoteStatus:
    run_id: str
    state: TaskState
    updated_at: float
    progress: str = ''
    artifacts: tuple[str, ...] = ()
    validation_evidence: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    cancellation_accepted: bool = False


class M2Client(Protocol):
    """Semantic client contract. A future adapter must use a supplied M2 contract."""
    def submit(self, request: TaskRequest) -> str: ...
    def status(self, run_id: str) -> RemoteStatus: ...
    def cancel(self, run_id: str) -> bool: ...
    def result(self, run_id: str) -> TaskResult | None: ...


def _encode(value) -> str:
    if isinstance(value, StrEnum):
        return value.value
    if hasattr(value, '__dataclass_fields__'):
        return json.dumps(asdict(value), sort_keys=True, separators=(',', ':'))
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


def _request_from(text: str) -> TaskRequest:
    data = json.loads(text)
    data['policies'] = tuple(PolicyRevision(**item) for item in data['policies'])
    for key in ('dependencies', 'relevant_decisions', 'acceptance_criteria', 'allowed_actions',
                'result_requirements', 'permitted_context'):
        data[key] = tuple(data[key])
    return TaskRequest(**data)


class SQLiteTaskStore:
    """Receipts, request snapshots, and append-only lifecycle events."""
    def __init__(self, database: str):
        self.db = sqlite3.connect(database, timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS task_receipts(
          task_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, project_id TEXT NOT NULL,
          thread_id TEXT NOT NULL, idempotency_key TEXT NOT NULL UNIQUE, request_json TEXT NOT NULL,
          run_id TEXT UNIQUE, state TEXT NOT NULL, progress TEXT NOT NULL DEFAULT '',
          artifacts TEXT NOT NULL DEFAULT '[]', validation_evidence TEXT NOT NULL DEFAULT '[]',
          errors TEXT NOT NULL DEFAULT '[]', result_json TEXT, cancellation_accepted INTEGER NOT NULL DEFAULT 0,
          revalidation_flags TEXT NOT NULL DEFAULT '[]', created_at REAL NOT NULL, updated_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS task_events(
          event_id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL REFERENCES task_receipts(task_id),
          kind TEXT NOT NULL, payload_json TEXT NOT NULL, created_at REAL NOT NULL);
        CREATE INDEX IF NOT EXISTS task_events_task ON task_events(task_id,event_id);
        ''')

    def close(self):
        self.db.close()

    def get(self, task_id: str) -> dict | None:
        row = self.db.execute('SELECT * FROM task_receipts WHERE task_id=?', (task_id,)).fetchone()
        return self._dict(row) if row else None

    def by_idempotency(self, key: str) -> dict | None:
        row = self.db.execute('SELECT * FROM task_receipts WHERE idempotency_key=?', (key,)).fetchone()
        return self._dict(row) if row else None

    @staticmethod
    def _dict(row):
        out = dict(row)
        out['request'] = _request_from(out.pop('request_json'))
        for key in ('artifacts', 'validation_evidence', 'errors', 'revalidation_flags'):
            out[key] = tuple(json.loads(out[key]))
        out['state'] = TaskState(out['state'])
        if out['result_json']:
            result = json.loads(out.pop('result_json'))
            for key in ('artifacts', 'validation_evidence', 'errors'):
                result[key] = tuple(result[key])
            out['result'] = TaskResult(**result)
        else:
            out.pop('result_json')
            out['result'] = None
        out['cancellation_accepted'] = bool(out['cancellation_accepted'])
        return out

    def list(self) -> tuple[dict, ...]:
        rows = self.db.execute('SELECT * FROM task_receipts ORDER BY created_at,task_id').fetchall()
        return tuple(self._dict(row) for row in rows)

    def events(self, task_id: str) -> tuple[dict, ...]:
        return tuple(dict(row) for row in self.db.execute(
            'SELECT kind,payload_json,created_at FROM task_events WHERE task_id=? ORDER BY event_id',
            (task_id,)).fetchall())

    def create(self, request: TaskRequest, state: TaskState = TaskState.QUEUED) -> dict:
        now = time.time()
        with self.db:
            self.db.execute('INSERT INTO task_receipts(task_id,user_id,project_id,thread_id,idempotency_key,'
                            'request_json,state,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)',
                            (request.task_id, request.user_id, request.project_id, request.thread_id,
                             request.idempotency_key, _encode(request), state.value, now, now))
            self._event(request.task_id, 'created', {'state': state.value})
        return self.get(request.task_id)

    def _event(self, task_id, kind, payload):
        self.db.execute('INSERT INTO task_events(task_id,kind,payload_json,created_at) VALUES(?,?,?,?)',
                        (task_id, kind, _encode(payload), time.time()))

    def update(self, task_id: str, *, kind: str, payload: Mapping, **fields) -> dict:
        allowed = {'run_id', 'state', 'progress', 'artifacts', 'validation_evidence', 'errors',
                   'result_json', 'cancellation_accepted', 'revalidation_flags'}
        if set(fields) - allowed:
            raise ValueError('Unsupported receipt field')
        values = {}
        for key, value in fields.items():
            if key == 'state' and isinstance(value, TaskState): value = value.value
            elif key in {'artifacts', 'validation_evidence', 'errors', 'revalidation_flags'}: value = _encode(value)
            values[key] = value
        values['updated_at'] = time.time()
        with self.db:
            if self.get(task_id) is None: raise TaskError('Unknown task')
            assignments = ','.join(f'{key}=?' for key in values)
            self.db.execute(f'UPDATE task_receipts SET {assignments} WHERE task_id=?',
                            (*values.values(), task_id))
            self._event(task_id, kind, payload)
        return self.get(task_id)


class FakeM2Client:
    """In-memory fake; call advance/fail/ask/cancel_confirmed to drive scenarios."""
    def __init__(self):
        self.runs: dict[str, dict] = {}
        self.idempotency: dict[str, str] = {}
        self.submit_count = 0

    def submit(self, request: TaskRequest) -> str:
        old = self.idempotency.get(request.idempotency_key)
        if old: return old
        run = 'fake-' + hashlib.sha256(request.idempotency_key.encode()).hexdigest()[:20]
        self.idempotency[request.idempotency_key] = run
        self.runs[run] = {'request': request, 'status': RemoteStatus(run, TaskState.RUNNING, time.time(), 'accepted'),
                          'result': None, 'cancel_requested': False}
        self.submit_count += 1
        return run

    def status(self, run_id: str) -> RemoteStatus:
        return self.runs[run_id]['status']

    def cancel(self, run_id: str) -> bool:
        item = self.runs[run_id]
        if item['status'].state in TERMINAL: return item['status'].state == TaskState.CANCELLED
        item['cancel_requested'] = True
        current = item['status']
        item['status'] = RemoteStatus(run_id, TaskState.CANCEL_REQUESTED, time.time(),
                                      'cancellation requested', current.artifacts,
                                      current.validation_evidence, current.errors, True)
        return True

    def result(self, run_id: str) -> TaskResult | None:
        return self.runs[run_id]['result']

    def advance(self, run_id: str, *, progress: str = 'working'):
        item = self.runs[run_id]; old = item['status']
        item['status'] = RemoteStatus(run_id, TaskState.RUNNING, time.time(), progress,
                                      old.artifacts, old.validation_evidence, old.errors)

    def awaiting_input(self, run_id: str, prompt: str):
        item = self.runs[run_id]; old = item['status']
        item['status'] = RemoteStatus(run_id, TaskState.AWAITING_INPUT, time.time(), prompt)

    def finish(self, run_id: str, result: TaskResult):
        item = self.runs[run_id]; item['result'] = result
        item['status'] = RemoteStatus(run_id, TaskState.SUCCEEDED if result.complete else TaskState.FAILED,
            time.time(), 'completed' if result.complete else 'partial result', result.artifacts,
            result.validation_evidence, result.errors)

    def fail(self, run_id: str, message: str):
        item = self.runs[run_id]
        item['status'] = RemoteStatus(run_id, TaskState.FAILED, time.time(), 'failed', errors=(message,))

    def confirm_cancelled(self, run_id: str):
        item = self.runs[run_id]
        item['status'] = RemoteStatus(run_id, TaskState.CANCELLED, time.time(), 'cancelled', cancellation_accepted=True)


class TaskOrchestrator:
    def __init__(self, store: SQLiteTaskStore, client: M2Client, *, max_concurrency: int = 2):
        if max_concurrency < 1: raise ValueError('max_concurrency must be positive')
        self.store, self.client, self.max_concurrency = store, client, max_concurrency

    def submit(self, request: TaskRequest) -> dict:
        prior = self.store.by_idempotency(request.idempotency_key)
        if prior:
            if prior['request'] != request: raise TaskError('Idempotency key already belongs to another request')
            return prior
        known = {item['task_id']: item for item in self.store.list()}
        if any(dep not in known for dep in request.dependencies): raise TaskError('Unknown task dependency')
        if any(known[dep]['request'].user_id != request.user_id or
               known[dep]['request'].project_id != request.project_id for dep in request.dependencies):
            raise TaskError('Dependencies must share user and project scope')
        receipt = self.store.create(request, TaskState.QUEUED)
        self._pump()
        return self.store.get(receipt['task_id'])

    def _conflicting_running(self, request: TaskRequest) -> bool:
        if not request.same_checkout: return False
        return any(item['state'] in {TaskState.RUNNING, TaskState.AWAITING_INPUT, TaskState.CANCEL_REQUESTED}
                   and item['request'].same_checkout
                   and item['request'].repository == request.repository
                   and item['request'].worktree == request.worktree for item in self.store.list())

    def _eligible(self, item: dict, records: Mapping[str, dict]) -> bool:
        if item['state'] != TaskState.QUEUED or item['run_id']: return False
        request = item['request']
        if self._conflicting_running(request): return False
        return all(records[dep]['state'] == TaskState.SUCCEEDED for dep in request.dependencies)

    def _pump(self):
        records = {x['task_id']: x for x in self.store.list()}
        active = sum(x['state'] in {TaskState.RUNNING, TaskState.AWAITING_INPUT,
                                    TaskState.CANCEL_REQUESTED} for x in records.values())
        for item in records.values():
            if active >= self.max_concurrency: break
            request = item['request']
            if any(records[d]['state'] in {TaskState.FAILED, TaskState.CANCELLED, TaskState.BLOCKED}
                   for d in request.dependencies):
                self.store.update(item['task_id'], kind='dependency_blocked',
                                  payload={'dependencies': request.dependencies}, state=TaskState.BLOCKED)
                continue
            if self._eligible(item, records):
                run_id = self.client.submit(request)
                self.store.update(item['task_id'], kind='submitted', payload={'run_id': run_id},
                                  run_id=run_id, state=TaskState.RUNNING, progress='submitted')
                active += 1

    def _sync(self, item: dict) -> dict:
        if not item['run_id'] or item['state'] in TERMINAL or item['state'] == TaskState.BLOCKED:
            return item
        remote = self.client.status(item['run_id'])
        fields = dict(state=remote.state, progress=remote.progress, artifacts=remote.artifacts,
                      validation_evidence=remote.validation_evidence, errors=remote.errors,
                      cancellation_accepted=remote.cancellation_accepted)
        result = self.client.result(item['run_id']) if remote.state in {TaskState.SUCCEEDED, TaskState.FAILED} else None
        if result is not None: fields['result_json'] = _encode(result)
        if remote.state == TaskState.SUCCEEDED and result is None:
            # A success without a retrievable result cannot be reported as verified success.
            fields.update(state=TaskState.FAILED, errors=(*remote.errors, 'Result unavailable'))
        elif remote.state == TaskState.SUCCEEDED and (not result.complete or
                not (result.validation_evidence or result.artifacts)):
            fields.update(state=TaskState.FAILED,
                          errors=(*remote.errors, 'Complete result evidence unavailable'))
        changed = any(item[key] != value for key, value in fields.items() if key in item and key != 'result_json')
        changed |= bool(fields.get('result_json') and item['result'] is None)
        if changed:
            item = self.store.update(item['task_id'], kind='remote_update', payload={
                'state': fields['state'], 'progress': remote.progress,
                'cancellation_accepted': remote.cancellation_accepted}, **fields)
        return item

    def status(self, task_id: str) -> dict:
        item = self.store.get(task_id)
        if item is None: raise TaskError('Unknown task')
        result = self._sync(item)
        self._pump()
        return result

    def result(self, task_id: str) -> TaskResult | None:
        item = self.status(task_id)
        return item['result']

    def cancel(self, task_id: str) -> dict:
        item = self.store.get(task_id)
        if item is None: raise TaskError('Unknown task')
        if item['state'] in TERMINAL: return item
        if item['state'] == TaskState.QUEUED:
            return self.store.update(task_id, kind='cancelled_before_submit', payload={}, state=TaskState.CANCELLED)
        accepted = self.client.cancel(item['run_id'])
        self.store.update(task_id, kind='cancel_requested', payload={'accepted': accepted},
                          state=TaskState.CANCEL_REQUESTED, cancellation_accepted=accepted)
        return self.status(task_id)

    def revalidate(self, task_id: str, flags: Sequence[str]) -> dict:
        item = self.store.get(task_id)
        if item is None: raise TaskError('Unknown task')
        return self.store.update(task_id, kind='revalidation', payload={'flags': tuple(flags)},
                                 revalidation_flags=tuple(flags))

    def reconcile(self) -> tuple[dict, ...]:
        """Refresh known runs after restart, retry unsent queued receipts idempotently."""
        for item in self.store.list():
            if item['run_id']:
                self._sync(item)
        self._pump()
        return self.store.list()
