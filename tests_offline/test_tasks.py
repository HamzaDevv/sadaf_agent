from dataclasses import replace

import pytest

from sadaf.tasks import (FakeM2Client, PolicyRevision, SQLiteTaskStore, TaskError,
                         TaskOrchestrator, TaskRequest, TaskResult, TaskState)


def request(task_id='task-a', *, project='project-a', repo='repo', worktree='checkout-a',
            deps=(), key=None, same=True):
    return TaskRequest(
        task_id=task_id, user_id='user-1', project_id=project, thread_id='thread-1',
        outcome='Implement the requested change', scope='Change the task API only',
        repository=repo, worktree=worktree, dependencies=tuple(deps),
        policies=(PolicyRevision('project-a', 'POLICIES.md', 'revision-17'),),
        relevant_decisions=('D002',), acceptance_criteria=('Offline checks pass',),
        allowed_actions=('Edit task module',), result_requirements=('Summary and validation evidence',),
        idempotency_key=key or task_id, same_checkout=same,
        permitted_context=('Only the task-relevant preference',))


@pytest.fixture
def setup(tmp_path):
    store = SQLiteTaskStore(str(tmp_path / 'tasks.sqlite3'))
    client = FakeM2Client()
    orchestrator = TaskOrchestrator(store, client, max_concurrency=2)
    yield store, client, orchestrator
    store.close()


def test_typed_request_validates_required_task_contract():
    with pytest.raises(ValueError, match='required'):
        replace(request(), acceptance_criteria=())
    with pytest.raises(ValueError, match='Dependencies'):
        replace(request(), dependencies=('task-a',))


def test_idempotent_submit_and_original_project_policy_attribution(setup):
    store, client, flow = setup
    original = request()
    first = flow.submit(original)
    duplicate = flow.submit(original)
    assert first['task_id'] == duplicate['task_id']
    assert client.submit_count == 1
    assert duplicate['request'].project_id == 'project-a'
    assert duplicate['request'].policies[0].revision == 'revision-17'
    with pytest.raises(TaskError, match='another request'):
        flow.submit(replace(original, project_id='project-b'))
    flow.revalidate('task-a', ('policy_changed_requires_revalidation',))
    loaded = store.get('task-a')
    assert loaded['request'].project_id == 'project-a'
    assert loaded['revalidation_flags'] == ('policy_changed_requires_revalidation',)


def test_same_checkout_mutations_queue_and_start_after_prior_completion(setup):
    _, client, flow = setup
    first = flow.submit(request('one'))
    second = flow.submit(request('two'))
    assert first['state'] == TaskState.RUNNING
    assert second['state'] == TaskState.QUEUED
    assert client.submit_count == 1
    client.finish(first['run_id'], TaskResult('done', validation_evidence=('checks passed',)))
    completed = flow.status('one')
    assert completed['state'] == TaskState.SUCCEEDED
    assert completed['result'].validation_evidence == ('checks passed',)
    assert flow.status('two')['state'] == TaskState.RUNNING
    assert client.submit_count == 2


def test_independent_work_respects_bounded_concurrency(setup):
    _, client, flow = setup
    a = flow.submit(request('a', worktree='a'))
    b = flow.submit(request('b', worktree='b'))
    c = flow.submit(request('c', worktree='c'))
    assert [a['state'], b['state'], c['state']] == [TaskState.RUNNING, TaskState.RUNNING, TaskState.QUEUED]
    assert client.submit_count == 2


def test_dependencies_wait_then_dispatch_and_failures_block(setup):
    _, client, flow = setup
    parent = flow.submit(request('parent', same=False))
    child = flow.submit(request('child', deps=('parent',), same=False))
    assert child['state'] == TaskState.QUEUED
    client.finish(parent['run_id'], TaskResult('parent complete', validation_evidence=('parent checks passed',)))
    flow.status('parent')
    assert flow.status('child')['state'] == TaskState.RUNNING
    other = flow.submit(request('other', same=False))
    blocked = flow.submit(request('blocked-child', deps=('other',), same=False))
    client.fail(other['run_id'], 'validation failed')
    flow.status('other')
    assert flow.status('blocked-child')['state'] == TaskState.BLOCKED
    assert blocked['state'] == TaskState.QUEUED


def test_restart_reconciles_receipt_without_duplicate_submission(setup):
    store, client, flow = setup
    first = flow.submit(request('restart-me', same=False))
    run_id = first['run_id']
    database = store.db.execute('PRAGMA database_list').fetchone()[2]
    store.close()
    restarted_store = SQLiteTaskStore(database)
    # The fake represents the same remote service process across client reconnects.
    restarted = TaskOrchestrator(restarted_store, client, max_concurrency=2)
    client.advance(run_id, progress='halfway')
    states = restarted.reconcile()
    assert states[0]['run_id'] == run_id
    assert states[0]['progress'] == 'halfway'
    assert client.submit_count == 1
    restarted_store.close()


def test_cancel_request_is_not_cancellation_completion(setup):
    _, client, flow = setup
    item = flow.submit(request('cancel-me', same=False))
    after_request = flow.cancel(item['task_id'])
    assert after_request['state'] == TaskState.CANCEL_REQUESTED
    assert after_request['cancellation_accepted'] is True
    client.confirm_cancelled(item['run_id'])
    assert flow.status(item['task_id'])['state'] == TaskState.CANCELLED


def test_awaiting_input_is_persisted_and_reconciled(setup):
    _, client, flow = setup
    item = flow.submit(request('needs-clarification', same=False))
    client.awaiting_input(item['run_id'], 'Which supported target should I use?')
    waiting = flow.status(item['task_id'])
    assert waiting['state'] == TaskState.AWAITING_INPUT
    assert waiting['progress'] == 'Which supported target should I use?'
    client.advance(item['run_id'], progress='resumed after clarification')
    assert flow.status(item['task_id'])['state'] == TaskState.RUNNING


def test_partial_result_and_success_without_result_are_not_claimed_success(setup):
    _, client, flow = setup
    partial = flow.submit(request('partial', same=False))
    client.finish(partial['run_id'], TaskResult('incomplete', errors=('one check failed',), complete=False))
    partial_status = flow.status('partial')
    assert partial_status['state'] == TaskState.FAILED
    assert partial_status['result'].summary == 'incomplete'
    assert partial_status['result'].errors == ('one check failed',)

    missing = flow.submit(request('missing', same=False))
    run = client.runs[missing['run_id']]
    run['status'] = replace(run['status'], state=TaskState.SUCCEEDED, progress='done')
    run['result'] = None
    missing_status = flow.status('missing')
    assert missing_status['state'] == TaskState.FAILED
    assert 'Result unavailable' in missing_status['errors']

    unverifiable = flow.submit(request('unverifiable', same=False))
    client.finish(unverifiable['run_id'], TaskResult('the work is done'))
    unverifiable_status = flow.status('unverifiable')
    assert unverifiable_status['state'] == TaskState.FAILED
    assert 'Complete result evidence unavailable' in unverifiable_status['errors']


def test_receipt_events_survive_restart_and_keep_original_scope(setup):
    store, client, flow = setup
    flow.submit(request('events', project='project-a', same=False))
    flow.revalidate('events', ('project_context_changed',))
    events = store.events('events')
    assert [event['kind'] for event in events] == ['created', 'submitted', 'revalidation']
    assert all(event['payload_json'] for event in events)
    assert store.get('events')['request'].project_id == 'project-a'
