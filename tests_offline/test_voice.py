import asyncio
import sqlite3

import pytest

from sadaf.conversation import (Completion, ContextBuilder, ConversationBackend,
    SQLiteConversationStore, ToolRuntime)
from sadaf.voice import FakeVoiceTransport, MacOSSpeechTransport, VoiceEvent, VoiceSession
from sadaf.voice_evaluation import CASES, Observation, evaluate


class Provider:
    def __init__(self, text='First sentence. Unheard secret suffix.'):
        self.text = text
        self.calls = []
        self.started = asyncio.Event()
        self.release = None
        self.failure = False

    async def complete(self, messages, *, tools=()):
        self.calls.append(messages)
        self.started.set()
        if self.release is not None: await self.release.wait()
        if self.failure: raise OSError('synthetic provider failure')
        return Completion(self.text)


def make(tmp_path, provider=None, transport=None, **kwargs):
    provider = provider or Provider()
    backend = ConversationBackend(store=SQLiteConversationStore(tmp_path/'threads.sqlite'),
        provider=provider, context_builder=ContextBuilder(), tool_runtime=ToolRuntime())
    return VoiceSession(backend,transport or FakeVoiceTransport(),user_id='u',thread_id='t',**kwargs), provider


def event(session, kind, id='', **kwargs): return VoiceEvent(kind, session.epoch, id, **kwargs)


@pytest.mark.asyncio
async def test_transcript_revisions_final_dedup_and_confirmed_prefix_history(tmp_path):
    session, provider = make(tmp_path)
    await session.connect()
    await session.handle(event(session,'transcript_partial','one',text='ticket 40'))
    await session.handle(event(session,'transcript_final','one',text=' ticket  407 ',revision=1))
    await session.drain()
    await session.handle(event(session,'transcript_final','one',text=' ticket  407 ',revision=1))
    await session.handle(event(session,'playback','one',played=15))
    await session.handle(event(session,'speech_started'))
    # Late player completion cannot turn an interrupted suffix into heard output.
    await session.handle(event(session,'playback','one',played=len(provider.text)))
    state = session.store.load('u','t')
    assert state.turns[0].text == 'ticket 407'
    assert 'First sentence.' in state.turns[1].text
    assert 'secret suffix' not in state.turns[1].text
    assert 'unheard' in state.turns[1].text
    with sqlite3.connect(session.store.db_path) as db:
        assert db.execute('SELECT raw,cleaned FROM voice_transcripts ORDER BY revision DESC').fetchone() == (' ticket  407 ', 'ticket 407')
    await session.handle(event(session,'transcript_final','one',text='ticket 408',revision=2))
    assert len(provider.calls) == 1  # Revised evidence never repeats tools.
    assert 'Transcript corrected after dispatch: ticket 408' in session.store.load('u','t').turns[0].text
    await session.handle(event(session,'transcript_final','two',text='continue'))
    await session.drain()
    assert 'secret suffix' not in repr(provider.calls[1])
    await session.shutdown()


@pytest.mark.asyncio
async def test_pause_during_generation_saves_unheard_and_shutdown_drains(tmp_path):
    provider = Provider()
    provider.release = asyncio.Event()
    session, _ = make(tmp_path,provider)
    await session.connect()
    await session.handle(event(session,'transcript_final','one',text='work'))
    await provider.started.wait()
    await session.pause()
    assert not session.listening
    provider.release.set()
    await session.drain()
    assert not [c for c in session.transport.commands if c[0]=='play']
    assert session.store.delivery('u','t','one')['status'] == 'stopped'
    assert provider.text not in repr(session.store.load('u','t'))
    await session.resume()
    await session.shutdown()
    assert session.closed and session.transport.commands[-1] == ('close',)


@pytest.mark.asyncio
async def test_reconnect_ignores_old_epoch_and_restart_does_not_replay(tmp_path):
    session, provider = make(tmp_path)
    await session.connect()
    await session.handle(event(session,'transcript_final','one',text='fixture'))
    await session.drain()
    old = event(session,'playback','one',played=len(provider.text))
    await session.handle(event(session,'disconnected'))
    await session.connect()
    await session.handle(old)
    assert session.store.delivery('u','t','one')['played'] == 0
    restarted, other = make(tmp_path)
    await restarted.connect()
    await restarted.handle(event(restarted,'transcript_final','one',text='fixture'))
    await restarted.drain()
    assert not other.calls
    assert 'unheard' in repr(restarted.store.load('u','t'))
    await session.shutdown()
    await restarted.shutdown()


@pytest.mark.asyncio
async def test_conflicting_revision_scope_guard_and_unknown_playback(tmp_path):
    session, _ = make(tmp_path,project_id='A')
    await session.connect()
    await session.handle(event(session,'transcript_partial','one',text='first'))
    with pytest.raises(ValueError,match='Conflicting'):
        await session.handle(event(session,'transcript_final','one',text='different'))
    await session.handle(event(session,'transcript_final','one',text='first'))
    await session.drain()
    await session.handle(event(session,'playback','unknown',played=100))
    with pytest.raises(ValueError,match='monotonic'):
        await session.handle(event(session,'playback','one',played=10000))
    with pytest.raises(ValueError,match='pinned'):
        make(tmp_path,project_id='B')
    await session.shutdown()


@pytest.mark.asyncio
async def test_provider_failure_and_bounded_reconnect(tmp_path):
    provider = Provider()
    provider.failure = True
    session, _ = make(tmp_path,provider)
    await session.connect()
    await session.handle(event(session,'transcript_final','one',text='fixture'))
    await session.drain()
    assert session.errors == ['backend_or_transport_failure']
    assert not session.store.load('u','t').turns
    class Broken(FakeVoiceTransport):
        async def connect(self, epoch):
            await super().connect(epoch)
            raise OSError('offline outage')
    broken, _ = make(tmp_path,transport=Broken())
    with pytest.raises(OSError): await broken.connect(attempts=2)
    assert len([c for c in broken.transport.commands if c[0]=='connect']) == 2
    assert not broken.connected
    await session.shutdown()


@pytest.mark.asyncio
async def test_mac_speech_fallback_no_shell_and_conservative_stop(tmp_path):
    with pytest.raises(ValueError,match='confirm_audio'):
        MacOSSpeechTransport()
    class Process:
        def __init__(self): self.returncode = None; self.done = asyncio.Event(); self.input = None
        async def communicate(self, text):
            self.input = text
            await self.done.wait()
        def terminate(self): self.returncode = -15; self.done.set()
    processes = []
    async def spawn(*args, **kwargs):
        assert args == ('/usr/bin/say',)
        proc = Process(); processes.append(proc); return proc
    transport = MacOSSpeechTransport(confirm_audio=True,spawn=spawn)
    session, provider = make(tmp_path,transport=transport)
    await session.connect()
    await session.handle(event(session,'transcript_final','one',text='fixture'))
    await session.drain()
    await asyncio.sleep(0)
    assert processes[0].input == provider.text.encode()
    await session.pause()
    stopped = await transport.receive()
    await session.handle(stopped)
    assert session.store.delivery('u','t','one')['played'] == 0
    await session.resume()
    await session.handle(event(session,'transcript_final','two',text='again'))
    await session.drain()
    processes[1].returncode = 0; processes[1].done.set()
    await session.handle(await transport.receive())
    assert session.store.delivery('u','t','two')['played'] == len(provider.text)
    await session.shutdown()


@pytest.mark.asyncio
async def test_evaluation_gates_and_identical_cases():
    calls = []
    async def runner(model, case):
        calls.append((model,case.id))
        return Observation(case.transcript, .2, .1, 3, None, None)
    with pytest.raises(ValueError,match='confirm_live'):
        await evaluate(runner,candidates=('fake-a',))
    with pytest.raises(ValueError,match='confirm_microphone'):
        await evaluate(runner,candidates=('fake-a',),confirm_live=True,microphone=True)
    assert calls == []
    rows = await evaluate(runner,candidates=('fake-a','fake-b'),confirm_live=True)
    assert len(rows) == len(CASES)*2
    assert [c[1] for c in calls[:3]] == [c[1] for c in calls[3:]]
    assert rows[0]['recognition_hits'] == ('Nila','407','12')


@pytest.mark.asyncio
async def test_shutdown_during_generation_keeps_backend_result_unheard(tmp_path):
    provider = Provider()
    provider.release = asyncio.Event()
    session, _ = make(tmp_path,provider)
    await session.connect()
    await session.handle(event(session,'transcript_final','one',text='fixture'))
    await provider.started.wait()
    shutdown = asyncio.create_task(session.shutdown())
    await asyncio.sleep(0)
    assert session.closed and not shutdown.done()
    provider.release.set()
    await shutdown
    assert session.store.delivery('u','t','one')['status'] == 'stopped'
    assert not [c for c in session.transport.commands if c[0]=='play']


@pytest.mark.asyncio
async def test_uncertain_restart_request_never_reexecutes_effects(tmp_path):
    session, provider = make(tmp_path)
    with sqlite3.connect(session.store.db_path) as db:
        db.execute("INSERT INTO voice_requests VALUES('u','t','uncertain','generating')")
    restarted, _ = make(tmp_path,provider)
    await restarted.connect()
    await restarted.handle(event(restarted,'transcript_final','uncertain',text='fixture'))
    await restarted.drain()
    assert not provider.calls
    with sqlite3.connect(restarted.store.db_path) as db:
        assert db.execute('SELECT state FROM voice_requests').fetchone()[0] == 'uncertain_restart'
    await restarted.shutdown()


@pytest.mark.asyncio
async def test_run_loop_reconnects_and_only_current_shutdown_stops(tmp_path):
    class AutoEvents(FakeVoiceTransport):
        async def connect(self, epoch):
            await super().connect(epoch)
            if len([c for c in self.commands if c[0]=='connect']) == 1:
                await self.events.put(VoiceEvent('disconnected',epoch))
                await self.events.put(VoiceEvent('shutdown',epoch))  # stale after reconnect
            else:
                await self.events.put(VoiceEvent('shutdown',epoch))
    transport = AutoEvents()
    session, _ = make(tmp_path,transport=transport)
    await session.run()
    assert len([c for c in transport.commands if c[0]=='connect']) == 2
    assert session.closed


@pytest.mark.asyncio
async def test_summary_receives_only_confirmed_playback(tmp_path):
    session, provider = make(tmp_path)
    observed = []
    async def summarize(state):
        observed.append(repr(state))
        return 'Earlier voice output had unconfirmed playback.'
    session.backend.summarizer = summarize
    session.backend.summarize_after_turns = 4
    session.backend.summary_keep_recent = 2
    await session.connect()
    for n in range(3):
        await session.handle(event(session,'transcript_final',str(n),text='fixture'))
        await session.drain()
    assert observed and provider.text not in observed[0]
    assert 'unheard' in observed[0]
    await session.shutdown()
