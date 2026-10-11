"""Local project context contracts. No stores or clients are opened at import.

Registry authorization is supplied by the application, never inferred from Markdown.
This module prepares context; it does not dispatch tasks or execute document content.
"""
from __future__ import annotations

from dataclasses import dataclass
import fcntl
import hashlib
from importlib.resources import files
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import time
from typing import Mapping, Protocol


DOCUMENTS = ('INDEX.md', 'PROJECT.md', 'POLICIES.md', 'ARCHITECTURE.md',
             'WORKING_STYLE.md', 'DECISIONS.md', 'OPEN_LOOPS.md')


class ContextError(ValueError):
    pass


class RevisionConflict(ContextError):
    pass


class PolicyBlocked(ContextError):
    pass


def _id(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,99}', value):
        raise ContextError('Invalid identity')
    return value


def _root(path: Path) -> Path:
    if path.is_symlink():
        raise ContextError('Context roots must not be symlinks')
    resolved = path.resolve(strict=True)
    if not resolved.is_dir():
        raise ContextError('Context root must be a directory')
    return resolved


def _overlap(a: Path, b: Path) -> bool:
    return a == b or a in b.parents or b in a.parents


@dataclass(frozen=True)
class Source:
    id: str
    root: Path
    owner: str
    authority: str  # project or organization; files cannot promote themselves


@dataclass(frozen=True)
class Project:
    user_id: str
    id: str
    context: Source
    repository: str
    organizations: tuple[Source, ...] = ()


class ProjectRegistry:
    """Durable identities and per-user/thread selection. Roots are explicitly allowed.

    Pass an independent development database and roots; never point at legacy data.
    Roots cannot overlap, including across users, to prevent content aliasing.
    """
    def __init__(self, database: Path, *, authorized_roots: tuple[Path, ...]):
        self.allowed = tuple(_root(p) for p in authorized_roots)
        self.db = sqlite3.connect(database)
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS context_sources(
          user_id TEXT, id TEXT, root TEXT UNIQUE, owner TEXT, authority TEXT,
          repository TEXT, organizations TEXT, PRIMARY KEY(user_id,id));
        CREATE TABLE IF NOT EXISTS project_sessions(
          user_id TEXT, thread_id TEXT, project_id TEXT,
          PRIMARY KEY(user_id,thread_id));
        ''')

    def close(self) -> None:
        self.db.close()

    def _authorized(self, root: Path) -> Path:
        root = _root(root)
        if not any(root == allowed or allowed in root.parents for allowed in self.allowed):
            raise ContextError('Context root is not authorized')
        return root

    def _register(self, user_id: str, source_id: str, root: Path, owner: str,
                  authority: str, repository: str, organizations: tuple[str, ...]) -> None:
        _id(user_id); _id(source_id); _id(owner)
        root = self._authorized(root)
        if not repository.strip() and authority == 'project':
            raise ContextError('Repository reference is required')
        for organization in organizations:
            row = self._row(user_id, organization)
            if row[3] != 'organization':
                raise ContextError('Only organization sources may be attached')
        try:
            with self.db:
                # Serialize validation with the write, including concurrent registries.
                self.db.execute('BEGIN IMMEDIATE')
                for (existing,) in self.db.execute('SELECT root FROM context_sources'):
                    if _overlap(root, Path(existing)):
                        raise ContextError('Registered context roots must not overlap')
                self.db.execute('INSERT INTO context_sources VALUES(?,?,?,?,?,?,?)',
                                (user_id, source_id, str(root), owner, authority,
                                 repository, json.dumps(organizations)))
        except sqlite3.IntegrityError:
            raise ContextError('Identity is already registered') from None

    def register_project(self, user_id: str, project_id: str, *, context_root: Path,
                         repository: str, owner: str,
                         organizations: tuple[str, ...] = ()) -> Project:
        self._register(user_id, project_id, context_root, owner, 'project', repository, organizations)
        return self.get(user_id, project_id)

    def register_organization(self, user_id: str, organization_id: str, *,
                              context_root: Path, owner: str) -> None:
        self._register(user_id, organization_id, context_root, owner, 'organization', '', ())

    def _row(self, user_id: str, source_id: str) -> tuple:
        row = self.db.execute('SELECT id,root,owner,authority,repository,organizations '
                              'FROM context_sources WHERE user_id=? AND id=?',
                              (_id(user_id), _id(source_id))).fetchone()
        if row is None:
            raise ContextError('Source is not registered in this user scope')
        self._authorized(Path(row[1]))
        return row

    def get(self, user_id: str, project_id: str) -> Project:
        row = self._row(user_id, project_id)
        if row[3] != 'project':
            raise ContextError('Expected a project')
        orgs = []
        for source_id in json.loads(row[5]):
            org = self._row(user_id, source_id)
            orgs.append(Source(org[0], Path(org[1]), org[2], org[3]))
        return Project(user_id, project_id, Source(row[0], Path(row[1]), row[2], row[3]),
                       row[4], tuple(sorted(orgs, key=lambda s: s.id)))

    def activate(self, user_id: str, thread_id: str, project_id: str,
                 context: ProjectContext) -> Snapshot:
        snapshot = context.refresh(self.get(user_id, project_id))
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO project_sessions VALUES(?,?,?)',
                            (user_id, _id(thread_id), project_id))
        return snapshot

    def active(self, user_id: str, thread_id: str) -> Project:
        row = self.db.execute('SELECT project_id FROM project_sessions '
                              'WHERE user_id=? AND thread_id=?',
                              (_id(user_id), _id(thread_id))).fetchone()
        if row is None:
            raise ContextError('No active project')
        return self.get(user_id, row[0])


@dataclass(frozen=True)
class Document:
    source_id: str
    project_id: str
    name: str
    revision: str
    text: str
    owner: str
    trust: str
    status: str = 'verified'


class DocumentSource(Protocol):
    def list(self) -> Mapping[str, str]: ...
    def read(self, name: str, revision: str) -> str: ...
    def update(self, name: str, text: str, *, expected_revision: str) -> str: ...


class LocalMarkdownSource:
    """Direct-child Markdown, SHA-256 revisions, retained revision reads and CAS.

    flock serializes cooperating local writers. Arbitrary external editors do not
    honor this lock: detected edits conflict, but cannot guarantee OS-level CAS.
    """
    def __init__(self, root: Path, revision_database: Path):
        self.root = _root(root)
        self.db = sqlite3.connect(revision_database)
        self.db.execute('CREATE TABLE IF NOT EXISTS document_versions('
                        'root TEXT,name TEXT,revision TEXT,text TEXT,'
                        'PRIMARY KEY(root,name,revision))')

    def close(self) -> None:
        self.db.close()

    def _path(self, name: str) -> Path:
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*\.md', name):
            raise ContextError('Only direct-child Markdown names are allowed')
        if _root(self.root) != self.root:
            raise ContextError('Context root changed')
        path = self.root / name
        if path.is_symlink() or path.resolve().parent != self.root:
            raise ContextError('Document symlink or path escape')
        return path

    def _current(self, name: str) -> tuple[str, str]:
        path = self._path(name)
        # O_NOFOLLOW also rejects a symlink swapped after the path check.
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, 'rb') as stream:
            raw = stream.read()
        text = raw.decode('utf-8')
        revision = hashlib.sha256(raw).hexdigest()
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO document_versions VALUES(?,?,?,?)',
                            (str(self.root), name, revision, text))
        return revision, text

    def list(self) -> Mapping[str, str]:
        _root(self.root)
        return {p.name: self._current(p.name)[0]
                for p in sorted(self.root.glob('*.md'))}

    def read(self, name: str, revision: str) -> str:
        self._path(name)  # Check boundaries even for a historical read.
        row = self.db.execute('SELECT text FROM document_versions '
                              'WHERE root=? AND name=? AND revision=?',
                              (str(self.root), name, revision)).fetchone()
        if row is not None:
            return row[0]
        current, text = self._current(name)
        if current != revision:
            raise RevisionConflict('Requested revision is unavailable')
        return text

    def update(self, name: str, text: str, *, expected_revision: str) -> str:
        path = self._path(name)
        lock = self.root / '.sadaf-context.lock'
        fd = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'w') as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            if self._current(name)[0] != expected_revision:
                raise RevisionConflict('Document changed; refresh before updating')
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(dir=self.root, delete=False) as stream:
                    temporary = Path(stream.name)
                    stream.write(text.encode('utf-8'))
                    stream.flush()
                    os.fsync(stream.fileno())
                if self._current(name)[0] != expected_revision:
                    raise RevisionConflict('Document changed during update')
                self._path(name)
                os.replace(temporary, path)
                return self._current(name)[0]
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)


def initialize_project(root: Path) -> None:
    """Create missing templates only. Existing Markdown is never replaced."""
    root = _root(root)
    for name in DOCUMENTS:
        path = root / name
        template = files('sadaf.project_templates').joinpath(name).read_text(encoding='utf-8')
        try:
            with path.open('x', encoding='utf-8') as stream:
                stream.write(template)
        except FileExistsError:
            if path.is_symlink() or not path.is_file():
                raise ContextError('Template target must be a regular file') from None


@dataclass(frozen=True)
class Snapshot:
    user_id: str
    project_id: str
    repository: str
    documents: tuple[Document, ...]
    verified_at: float

    @property
    def policy_revisions(self) -> tuple[tuple[str, str], ...]:
        return tuple((f'{d.source_id}/{d.name}', d.revision) for d in self.documents
                     if d.trust in {'organization_policy', 'project_policy'})


@dataclass(frozen=True)
class Rule:
    key: str
    value: str
    sources: tuple[str, ...]


@dataclass(frozen=True)
class ContextPacket:
    snapshot: Snapshot
    binding_documents: tuple[Document, ...]
    rules: tuple[Rule, ...]
    preferences: tuple[tuple[str, str], ...]
    working_style: tuple[Document, ...]
    knowledge: tuple[tuple[Document, str], ...]


def _entries(text: str, *, mandatory: bool) -> dict[str, str]:
    result = {}
    fenced = False
    for line in text.splitlines():
        if line.lstrip().startswith(('```', '~~~')):
            fenced = not fenced
        if fenced:
            continue
        prefix = '- MUST ' if mandatory else '- '
        if not line.startswith(prefix):
            continue
        match = re.fullmatch(r'([a-z][a-z0-9_.-]*)\s*=\s*(\S.*)', line[len(prefix):])
        if not match:
            if mandatory:
                raise PolicyBlocked('Malformed mandatory rule')
            continue
        key, value = match.groups()
        if key in result and result[key] != value:
            raise PolicyBlocked('Conflicting rules within a document')
        result[key] = value
    return result


class ProjectContext:
    def __init__(self, sources: Mapping[tuple[str, str], DocumentSource], *,
                 policy_budget: int = 16000, max_age: float = 60):
        # Copies prevent a caller changing the source map under a snapshot read.
        self.sources = dict(sources)
        if policy_budget <= 0 or max_age <= 0:
            raise ContextError('Budgets and cache age must be positive')
        self.policy_budget = policy_budget
        self.max_age = max_age

    def _source(self, user_id: str, source_id: str) -> DocumentSource:
        try:
            return self.sources[user_id, source_id]
        except KeyError:
            raise PolicyBlocked('Required document source is unavailable') from None

    def _bound_source(self, user_id: str, source: Source) -> DocumentSource:
        adapter = self._source(user_id, source.id)
        if isinstance(adapter, LocalMarkdownSource) and adapter.root != source.root:
            raise PolicyBlocked('Local adapter does not match the registered root')
        return adapter

    def refresh(self, project: Project) -> Snapshot:
        """Double-collect manifests around exact revision reads; never use cache fallback."""
        sources = (*project.organizations, project.context)
        try:
            for _ in range(3):
                manifests = [(s, dict(self._bound_source(project.user_id, s).list())) for s in sources]
                documents = []
                for source, manifest in manifests:
                    if 'POLICIES.md' not in manifest:
                        raise PolicyBlocked('Required POLICIES.md is missing')
                    names = sorted(manifest) if source.authority == 'project' else ['POLICIES.md']
                    for name in names:
                        text = self._bound_source(project.user_id, source).read(name, manifest[name])
                        trust = ('organization_policy' if source.authority == 'organization'
                                 else 'project_policy') if name == 'POLICIES.md' else (
                                     'working_style' if name == 'WORKING_STYLE.md' else
                                     'project_knowledge' if name in DOCUMENTS else 'untrusted')
                        documents.append(Document(source.id, project.id, name, manifest[name],
                                                  text, source.owner, trust))
                if all(dict(self._bound_source(project.user_id, s).list()) == manifest
                       for s, manifest in manifests):
                    snapshot = Snapshot(project.user_id, project.id, project.repository,
                                        tuple(documents), time.time())
                    self.assemble(snapshot)  # Conflicts and size block activation/dispatch too.
                    return snapshot
            raise PolicyBlocked('Documents changed during snapshot; retry after edits settle')
        except (OSError, UnicodeError, RevisionConflict) as exc:
            raise PolicyBlocked('Required context could not be verified') from exc

    def prepare_dispatch(self, registry: ProjectRegistry, *, user_id: str,
                         project_id: str, keywords: tuple[str, ...] = (),
                         global_preferences: Mapping[str, str] | None = None) -> ContextPacket:
        # Explicit original project, never implicitly follow an active-session switch.
        try:
            project = registry.get(user_id, project_id)
        except (OSError, ContextError) as exc:
            raise PolicyBlocked('Registered project context is unavailable') from exc
        snapshot = self.refresh(project)
        return self.assemble(snapshot, keywords=keywords, global_preferences=global_preferences)

    def assemble(self, snapshot: Snapshot, *, keywords: tuple[str, ...] = (),
                 global_preferences: Mapping[str, str] | None = None) -> ContextPacket:
        if not 0 <= time.time() - snapshot.verified_at <= self.max_age:
            raise PolicyBlocked('Snapshot is stale; refresh required policies')
        binding = tuple(d for d in snapshot.documents if d.trust.endswith('_policy'))
        if not binding or any(d.status != 'verified' for d in binding):
            raise PolicyBlocked('Required policies are unverified')
        if sum(len(d.text) for d in binding) > self.policy_budget:
            raise PolicyBlocked('Binding policies exceed reserved character budget')
        values: dict[str, tuple[str, list[str]]] = {}
        for document in binding:
            for key, value in _entries(document.text, mandatory=True).items():
                source = f'{document.source_id}/{document.name}@{document.revision}'
                if key in values and values[key][0] != value:
                    raise PolicyBlocked(f'Conflicting mandatory rule: {key}')
                values.setdefault(key, (value, []))[1].append(source)
        styles = tuple(d for d in snapshot.documents if d.trust == 'working_style')
        preferences = dict(global_preferences or {})
        for style in styles:
            preferences.update(_entries(style.text, mandatory=False))
        preferences.update({k: v[0] for k, v in values.items()})
        knowledge = []
        for document in snapshot.documents:
            if document.trust not in {'project_knowledge', 'untrusted'}:
                continue
            sections = re.split(r'(?m)(?=^#{1,6} )', document.text)
            for section in sections:
                if section.strip() and any(k.casefold() in section.casefold() for k in keywords if k):
                    knowledge.append((document, section))
        return ContextPacket(snapshot, binding,
                             tuple(Rule(k, v, tuple(s)) for k, (v, s) in sorted(values.items())),
                             tuple(sorted(preferences.items())), styles, tuple(knowledge))

    def revalidate(self, registry: ProjectRegistry, snapshot: Snapshot) -> tuple[str, ...]:
        """Running tasks keep their original scope; changed policy requires a pause/review."""
        try:
            current = self.refresh(registry.get(snapshot.user_id, snapshot.project_id))
        except (ContextError, OSError):
            return ('required_context_unavailable',)
        if current.policy_revisions != snapshot.policy_revisions:
            return ('policy_changed_requires_revalidation',)
        if current.documents != snapshot.documents:
            return ('project_context_changed',)
        return ()

    def update_document(self, registry: ProjectRegistry, *, user_id: str, project_id: str,
                        source_id: str, name: str, text: str, expected_revision: str,
                        actor: str, reason: str) -> str:
        """Explicit owner-authorized workflow; caller authenticates actor out of band.

        No conversational/extraction method calls this automatically. Organization
        policy updates target the shared source and affect all attached projects.
        """
        project = registry.get(user_id, project_id)
        source = next((s for s in (*project.organizations, project.context) if s.id == source_id), None)
        if source is None or actor != source.owner or not reason.strip():
            raise ContextError('Document update requires its owner and an explicit reason')
        if source.authority == 'organization' and name != 'POLICIES.md':
            raise ContextError('Organization source exposes only its policy')
        if name == 'POLICIES.md':
            _entries(text, mandatory=True)
        return self._bound_source(user_id, source).update(name, text, expected_revision=expected_revision)
