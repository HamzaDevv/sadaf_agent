"""One synthetic vertical slice across the actual milestone 2–6 libraries."""
from dataclasses import replace

import pytest

from sadaf.conversation import (ContextBuilder, ConversationBackend, ProjectContextLoader,
    SQLiteConversationStore, ToolRuntime)
from sadaf.memory import MemoryStore
from sadaf.projects import (LocalMarkdownSource, ProjectContext, ProjectRegistry, initialize_project)
from sadaf.tasks import FakeM2Client, PolicyRevision, SQLiteTaskStore, TaskOrchestrator, TaskResult, TaskState
from sadaf.voice import FakeVoiceTransport, VoiceSession
from test_tasks import request
from test_voice import Provider, event


@pytest.mark.asyncio
async def test_integrated_correction_switch_tasks_interruption_and_restart(tmp_path):
    roots = tmp_path/'projects'
    roots.mkdir()
    registry = ProjectRegistry(tmp_path/'registry.sqlite',authorized_roots=(roots,))
    sources = {}
    for name in ('A','B'):
        root = roots/name
        root.mkdir()
        initialize_project(root)
        (root/'POLICIES.md').write_text(f'# Binding\n- MUST target={name}\nRetain the whole {name} rule document.')
        (root/'ARCHITECTURE.md').write_text(f'# engine\n{name} private engine')
        sources['u',name] = LocalMarkdownSource(root,tmp_path/'versions.sqlite')
        registry.register_project('u',name,context_root=root,repository=f'fixture://{name}',owner='u')
    project_context = ProjectContext(sources)
    snapshot = registry.activate('u','a','A',project_context)
    pins = tuple(PolicyRevision(d.source_id,d.name,d.revision) for d in snapshot.documents if d.trust.endswith('_policy'))
    memory = MemoryStore(tmp_path/'memory'/'store.sqlite')
    episode = memory.add_episode('u','Synthetic language preference',turn_id='preference')
    fact = memory.record_fact('u','preferences','language','English',status='confirmed',allow_export=True,
        source_episode_id=episode.id,source_turn_id='preference')
    task_store = SQLiteTaskStore(str(tmp_path/'tasks.sqlite'))
    client = FakeM2Client()
    flow = TaskOrchestrator(task_store,client)
    receipts = []
    for name in ('one','two'):
        receipts.append(flow.submit(replace(request(name,project='A',worktree=name),
            user_id='u',thread_id='a',policies=pins)))
    assert all(r['state'] == TaskState.RUNNING for r in receipts)
    provider = Provider('Verified fixture response. Unheard remainder.')
    store = SQLiteConversationStore(tmp_path/'threads.sqlite')
    def backend():
        return ConversationBackend(store=store,provider=provider,context_builder=ContextBuilder(),
            tool_runtime=ToolRuntime(),memory_repository=memory,
            context_loader=ProjectContextLoader(registry,project_context),
            task_state_loader=lambda u,t,p: flow.conversation_state(u,t,p))
    a = VoiceSession(backend(),FakeVoiceTransport(),user_id='u',thread_id='a',project_id='A')
    await a.connect()
    await a.handle(event(a,'transcript_final','a1',text='language engine'))
    await a.drain()
    assert 'English' in repr(provider.calls[-1])
    assert 'Retain the whole A rule document.' in repr(provider.calls[-1])
    assert 'Task one project=A state=running' in repr(provider.calls[-1])
    await a.handle(event(a,'playback','a1',played=len('Verified fixture response.')))
    await a.pause()
    assert all(flow.status(r['task_id'])['state'] == TaskState.RUNNING for r in receipts)
    assert all(not flow.store.get(r['task_id'])['cancellation_accepted'] for r in receipts)
    memory.add_episode('u','Synthetic correction',turn_id='correction')
    memory.correct_fact(fact,'Hindi',source_turn_id='correction')
    registry.activate('u','b','B',project_context)
    b = VoiceSession(backend(),FakeVoiceTransport(),user_id='u',thread_id='b',project_id='B')
    await b.connect()
    await b.handle(event(b,'transcript_final','b1',text='language engine'))
    await b.drain()
    prompt = repr(provider.calls[-1])
    assert 'Hindi' in prompt and 'English' not in prompt
    assert 'Retain the whole B rule document.' in prompt
    assert 'A private engine' not in prompt and 'Task one' not in prompt
    client.finish(receipts[0]['run_id'],TaskResult('simulated completion',validation_evidence=('fake offline check',)))
    client.finish(receipts[1]['run_id'],TaskResult('success string without evidence'))
    task_store.close()
    task_store = SQLiteTaskStore(str(tmp_path/'tasks.sqlite'))
    flow = TaskOrchestrator(task_store,client)
    flow.reconcile()
    assert client.submit_count == 2
    assert flow.status('one')['state'] == TaskState.SUCCEEDED
    assert flow.status('two')['state'] == TaskState.FAILED
    assert flow.status('one')['request'].project_id == 'A'
    assert flow.status('one')['request'].policies == pins
    await a.shutdown()
    await b.shutdown()
    memory = MemoryStore(tmp_path/'memory'/'store.sqlite')
    store = SQLiteConversationStore(tmp_path/'threads.sqlite')
    restarted = VoiceSession(backend(),FakeVoiceTransport(),user_id='u',thread_id='a',project_id='A')
    await restarted.connect()
    await restarted.handle(event(restarted,'transcript_final','a1',text='language engine'))
    await restarted.drain()
    assert len(provider.calls) == 2
    await restarted.handle(event(restarted,'transcript_final','a2',text='language task results'))
    await restarted.drain()
    prompt = repr(provider.calls[-1])
    assert 'Hindi' in prompt and 'Unheard remainder' not in prompt
    assert 'project=A state=succeeded' in prompt and 'project=A state=failed' in prompt
    assert 'fake offline check' in prompt
    assert 'Complete result evidence unavailable' in prompt
    assert 'Retain the whole A rule document.' in prompt  # Still A after active selection B.
    await restarted.shutdown()
    task_store.close()
    registry.close()
    for source in sources.values(): source.close()


def test_success_with_errors_is_not_reported_as_success(tmp_path):
    store = SQLiteTaskStore(str(tmp_path/'tasks.sqlite'))
    client = FakeM2Client()
    flow = TaskOrchestrator(store,client)
    receipt = flow.submit(request())
    client.finish(receipt['run_id'],TaskResult('done',validation_evidence=('one check passed',),errors=('another failed',)))
    assert flow.status(receipt['task_id'])['state'] == TaskState.FAILED
    assert 'another failed' in flow.status(receipt['task_id'])['errors']
    store.close()


@pytest.mark.asyncio
async def test_voice_cannot_bypass_missing_binding_policy(tmp_path):
    from sadaf.projects import PolicyBlocked
    provider = Provider()
    def unavailable(*args): raise PolicyBlocked('Synthetic mandatory policy unavailable')
    backend = ConversationBackend(store=SQLiteConversationStore(tmp_path/'threads.sqlite'),
        provider=provider,context_builder=ContextBuilder(),tool_runtime=ToolRuntime(),
        context_loader=unavailable)
    session = VoiceSession(backend,FakeVoiceTransport(),user_id='u',thread_id='t',project_id='A')
    await session.connect()
    await session.handle(event(session,'transcript_final','one',text='make the change'))
    await session.drain()
    assert not provider.calls
    assert session.errors == ['backend_or_transport_failure']
    assert not session.store.load('u','t').turns
    await session.shutdown()
