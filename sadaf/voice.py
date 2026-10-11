"""Application-owned voice lifecycle. No hardware/provider work at import time."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import sqlite3
import uuid
from typing import Protocol, Mapping

from .conversation import ConversationBackend, SQLiteConversationStore


@dataclass(frozen=True)
class VoiceEvent:
    kind: str
    epoch: int
    id: str = ""
    text: str = ""
    revision: int = 0
    played: int = 0


class VoiceTransport(Protocol):
    async def connect(self, epoch: int) -> None: ...
    async def listen(self, enabled: bool) -> None: ...
    async def sync(self, context: Mapping) -> None: ...
    async def play(self, delivery_id: str, text: str, epoch: int) -> None: ...
    async def stop(self) -> None: ...
    async def close(self) -> None: ...
    async def receive(self) -> VoiceEvent: ...


class FakeVoiceTransport:
    """Explicit events; play never automatically acknowledges hearing."""
    def __init__(self):
        self.events = asyncio.Queue()
        self.commands = []

    async def connect(self, epoch): self.commands.append(("connect", epoch))
    async def listen(self, enabled): self.commands.append(("listen", enabled))
    async def sync(self, context): self.commands.append(("sync", dict(context)))
    async def play(self, delivery_id, text, epoch): self.commands.append(("play", delivery_id, text, epoch))
    async def stop(self): self.commands.append(("stop",))
    async def close(self): self.commands.append(("close",))
    async def receive(self): return await self.events.get()


class MacOSSpeechTransport(FakeVoiceTransport):
    """Text input + /usr/bin/say output; no microphone or recognition.

    Only clean subprocess completion acknowledges the full output. Interrupted
    output has no known word boundary and is conservatively left unconfirmed.
    """
    def __init__(self, *, confirm_audio: bool = False, spawn=None):
        if not confirm_audio: raise ValueError("macOS audio requires confirm_audio=True")
        super().__init__()
        self.spawn = spawn or asyncio.create_subprocess_exec
        self.process = None
        self.waiter = None

    async def play(self, delivery_id, text, epoch):
        await self.stop()
        self.process = await self.spawn('/usr/bin/say', stdin=asyncio.subprocess.PIPE)
        process = self.process
        async def finish():
            await process.communicate(text.encode('utf-8'))
            if process.returncode == 0:
                await self.events.put(VoiceEvent('playback', epoch, delivery_id, played=len(text)))
            else:
                await self.events.put(VoiceEvent('playback_stopped', epoch, delivery_id))
        self.waiter = asyncio.create_task(finish())

    async def stop(self):
        if self.process is not None and self.process.returncode is None:
            self.process.terminate()
        if self.waiter is not None:
            try:
                await asyncio.wait_for(asyncio.shield(self.waiter), 1)
            except TimeoutError:
                self.process.kill()
                await asyncio.wait_for(asyncio.shield(self.waiter), 1)
        self.process = self.waiter = None

    async def close(self): await self.stop()


class VoiceSession:
    """Voice pause/interrupt never calls an M2 cancellation method.

    Final transcripts trigger bounded backend work in separate asyncio tasks.
    Backend/tool work continues when speech is interrupted; its late result is
    saved as unheard. Scope switching requires a new VoiceSession/thread.
    """
    def __init__(self, backend: ConversationBackend, transport: VoiceTransport, *,
                 user_id: str, thread_id: str, project_id: str | None = None,
                 context: Mapping | None = None):
        if not isinstance(backend.store, SQLiteConversationStore):
            raise ValueError('Voice requires SQLiteConversationStore delivery tracking')
        self.backend, self.store, self.transport = backend, backend.store, transport
        self.user_id, self.thread_id, self.project_id = user_id, thread_id, project_id
        self.context = dict(context or {})
        if {'user_id','thread_id','project_id','text','delivery_id'} & self.context.keys():
            raise ValueError('Voice scope and transcript cannot be overridden')
        previous = self.store.load(user_id, thread_id)
        if previous.turns and previous.project_id != project_id:
            raise ValueError("Thread project is pinned; use a new thread for voice switching")
        self.epoch = uuid.uuid4().int
        self.generation = 0
        self.connected = self.paused = self.closed = False
        self.listening = False
        self.current = None
        self.jobs = set()
        self.errors = []  # Sanitized error kinds, never raw provider exceptions.
        self.control = asyncio.Lock()
        self.reasoning = asyncio.Lock()
        with sqlite3.connect(self.store.db_path) as db:
            db.executescript('''
              CREATE TABLE IF NOT EXISTS voice_transcripts(user_id TEXT,thread_id TEXT,id TEXT,revision INTEGER,raw TEXT,cleaned TEXT,final INTEGER,PRIMARY KEY(user_id,thread_id,id,revision));
              CREATE TABLE IF NOT EXISTS voice_requests(user_id TEXT,thread_id TEXT,id TEXT,state TEXT,PRIMARY KEY(user_id,thread_id,id));
            ''')
            # An uncertain interrupted request must never silently replay tool effects.
            db.execute("UPDATE voice_requests SET state='uncertain_restart' WHERE user_id=? AND thread_id=? AND state='generating'", (user_id,thread_id))
            pending = db.execute("SELECT delivery_id,played FROM voice_delivery WHERE user_id=? AND thread_id=? AND status='pending'", (user_id,thread_id)).fetchall()
        for delivery_id, played in pending:
            self.store.acknowledge_playback(user_id,thread_id,delivery_id,played,stopped=True)

    async def _sync(self):
        state = self.store.load(self.user_id, self.thread_id)
        await self.transport.sync({'user_id': self.user_id, 'thread_id': self.thread_id,
            'project_id': self.project_id, 'epoch': self.epoch,
            'commitments': state.commitments,
            'task_state': tuple(self.backend.task_state_loader(self.user_id,self.thread_id,self.project_id)) if self.backend.task_state_loader else (),
            'turns': tuple((t.speaker,t.text) for t in state.turns[-6:]),
            'note': 'Only confirmed playback is represented as spoken. Backend owns policies and task authority.'})

    async def synchronize(self):
        """Host calls after durable task reconciliation or commitment changes."""
        async with self.control:
            if self.connected and not self.closed:
                await self._sync()

    async def _interrupt(self):
        self.generation += 1
        if self.current:
            record = self.store.delivery(self.user_id,self.thread_id,self.current)
            self.store.acknowledge_playback(self.user_id,self.thread_id,self.current,record['played'],stopped=True)
            self.current = None
        try:
            await self.transport.stop()
        except (OSError, TimeoutError):
            self.errors.append("playback_stop_failure")
            self.connected = self.listening = False

    async def connect(self, *, attempts: int = 3, timeout: float = 5):
        if not 1 <= attempts <= 5: raise ValueError('Reconnect attempts must be bounded')
        async with self.control:
            if self.closed: raise RuntimeError('Voice session is closed')
            await self._interrupt()
            self.connected = False
            self.epoch += 1
            for attempt in range(attempts):
                try:
                    await asyncio.wait_for(self.transport.connect(self.epoch), timeout)
                    await asyncio.wait_for(self._sync(), timeout)
                    await asyncio.wait_for(self.transport.listen(not self.paused), timeout)
                    self.connected = True
                    self.listening = not self.paused
                    return
                except (OSError, TimeoutError):
                    await self.transport.close()
                    if attempt == attempts - 1: raise

    async def pause(self):
        async with self.control:
            if self.closed: return
            self.paused = True
            self.listening = False
            await self._interrupt()
            await self.transport.listen(False)

    async def resume(self):
        async with self.control:
            if self.closed or not self.connected: raise RuntimeError('Voice is disconnected')
            await self._sync()
            await self.transport.listen(True)
            self.paused = False
            self.listening = True

    def _transcript(self, event):
        if not event.id or event.revision < 0: raise ValueError('Invalid transcript identity')
        cleaned = ' '.join(event.text.split())
        with sqlite3.connect(self.store.db_path) as db:
            db.execute('BEGIN IMMEDIATE')
            previous = db.execute('SELECT revision,raw,final FROM voice_transcripts WHERE user_id=? AND thread_id=? AND id=? ORDER BY revision DESC LIMIT 1', (self.user_id,self.thread_id,event.id)).fetchone()
            if previous and event.revision < previous[0]: return False
            final = event.kind == 'transcript_final'
            if previous and event.revision == previous[0]:
                if previous[1] != event.text: raise ValueError('Conflicting transcript revision')
                if previous[2] or not final: return False
                db.execute('UPDATE voice_transcripts SET final=1 WHERE user_id=? AND thread_id=? AND id=? AND revision=?', (self.user_id,self.thread_id,event.id,event.revision))
            else:
                db.execute('INSERT INTO voice_transcripts VALUES(?,?,?,?,?,?,?)', (self.user_id,self.thread_id,event.id,event.revision,event.text,cleaned,int(final)))
            if not final or not cleaned: return False
            # Later final corrections are kept as evidence but never rerun tools.
            cursor = db.execute("INSERT OR IGNORE INTO voice_requests VALUES(?,?,?,'generating')", (self.user_id,self.thread_id,event.id))
            return cursor.rowcount == 1

    def _reconcile_transcript(self, utterance_id):
        with sqlite3.connect(self.store.db_path) as db:
            db.execute('BEGIN IMMEDIATE')
            rows = db.execute('SELECT cleaned FROM voice_transcripts WHERE user_id=? AND thread_id=? AND id=? AND final=1 ORDER BY revision', (self.user_id,self.thread_id,utterance_id)).fetchall()
            delivery = db.execute('SELECT seq FROM voice_delivery WHERE user_id=? AND thread_id=? AND delivery_id=?', (self.user_id,self.thread_id,utterance_id)).fetchone()
            if delivery and rows and rows[-1][0] != rows[0][0]:
                text = rows[0][0] + "\n[Transcript corrected after dispatch: " + rows[-1][0] + "; earlier tool effects used the original transcript and require review.]"
                db.execute('UPDATE conversation_turns SET text=? WHERE user_id=? AND thread_id=? AND seq=?', (text,self.user_id,self.thread_id,delivery[0]-1))

    async def handle(self, event: VoiceEvent):
        async with self.control:
            if self.closed or event.epoch != self.epoch: return
            if event.kind == 'disconnected':
                self.connected = self.listening = False
                await self._interrupt()
                return
            if not self.connected: return
            if event.kind == 'playback' and event.id == self.current:
                self.store.acknowledge_playback(self.user_id,self.thread_id,event.id,event.played)
                if self.store.delivery(self.user_id,self.thread_id,event.id)['status'] == 'played':
                    self.current = None
                await self._sync()
            elif event.kind == 'playback_stopped' and event.id == self.current:
                await self._interrupt()
                await self._sync()
            elif not self.paused:
                if event.kind == 'speech_started':
                    self.listening = True
                    await self._interrupt()
                    await self._sync()
                elif event.kind == 'speech_stopped': self.listening = False
                elif event.kind in ('transcript_partial', 'transcript_final'):
                    dispatch = self._transcript(event)
                    self._reconcile_transcript(event.id)
                    if dispatch:
                        await self._interrupt()
                        token = self.generation
                        job = asyncio.create_task(self._respond(event, token))
                        self.jobs.add(job)
                        job.add_done_callback(self.jobs.discard)
                    else:
                        await self._sync()

    async def _respond(self, event, token):
        try:
            async with self.reasoning:
                result = await self.backend.respond(user_id=self.user_id,thread_id=self.thread_id,
                    project_id=self.project_id,text=' '.join(event.text.split()),delivery_id=event.id,**self.context)
            self._reconcile_transcript(event.id)
            with sqlite3.connect(self.store.db_path) as db:
                db.execute("UPDATE voice_requests SET state='complete' WHERE user_id=? AND thread_id=? AND id=?", (self.user_id,self.thread_id,event.id))
            async with self.control:
                if self.closed or self.paused or not self.connected or token != self.generation:
                    self.store.acknowledge_playback(self.user_id,self.thread_id,event.id,0,stopped=True)
                    return
                self.current = event.id
                await self._sync()
                await self.transport.play(event.id,result.text,self.epoch)
        except Exception:
            self.errors.append('backend_or_transport_failure')
            with sqlite3.connect(self.store.db_path) as db:
                db.execute("UPDATE voice_requests SET state='failed' WHERE user_id=? AND thread_id=? AND id=?", (self.user_id,self.thread_id,event.id))
            async with self.control:
                if self.current == event.id:
                    await self._interrupt()
                else:
                    record = self.store.delivery(self.user_id,self.thread_id,event.id)
                    if record and record['status'] == 'pending':
                        self.store.acknowledge_playback(self.user_id,self.thread_id,event.id,record['played'],stopped=True)

    async def drain(self):
        if self.jobs: await asyncio.gather(*tuple(self.jobs))

    async def run(self):
        try:
            await self.connect()
            while not self.closed:
                event = await self.transport.receive()
                if event.epoch != self.epoch: continue
                if event.kind == 'shutdown': break
                await self.handle(event)
                if event.kind == 'disconnected':
                    await self.connect()
        finally:
            await self.shutdown()

    async def shutdown(self):
        try:
            async with self.control:
                if self.closed: return
                self.closed = True
                self.connected = self.listening = False
                await self._interrupt()
                try:
                    await self.transport.listen(False)
                finally:
                    await self.transport.close()
        finally:
            await self.drain()  # Backend saves unheard results; M2 is untouched.
