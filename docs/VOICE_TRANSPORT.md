# Voice transport and offline integration

Milestone 6 adds `sadaf.voice` around `ConversationBackend`. It is a standalone
application interface; the legacy `main.py` audio loop is unchanged. Imports
start no provider, microphone, speech process, task service, or memory store.

## Construction and host responsibilities

Construct the existing backend with an explicitly chosen new-data
`SQLiteConversationStore`, injected provider, tools, memory repository, and
`ProjectContextLoader`. Inject `task_state_loader=flow.conversation_state` to
refresh scoped durable task observations each turn. The host reconciles M2
separately; context loading itself performs no remote task poll.

```python
from sadaf.voice import FakeVoiceTransport, VoiceEvent, VoiceSession

transport = FakeVoiceTransport()
voice = VoiceSession(backend, transport, user_id="fixture-user",
                     thread_id="fixture-thread", project_id="fixture-project")
await voice.connect()
await voice.handle(VoiceEvent("transcript_final", voice.epoch,
                             "utterance-1", text="Synthetic task question"))
await voice.drain()
# Fake play records a command, but acknowledges no playback automatically.
# A real player emits only text prefixes known to have finished playback.
await voice.pause()
await voice.resume()
await voice.shutdown()
```

Alternatively `await voice.run()` consumes transport events, reconnects with
bounded attempts on disconnect, and closes on a current-session shutdown event.
Adapters implement connect/listen/sync/play/stop/close/receive. `play` starts
playback and returns promptly; playback progress arrives as events. All events
carry the application's connection epoch; IDs identify utterances/deliveries.
One host owns a user/thread voice session at a time. Project switching creates
a new thread/session, rather than redirecting previous history or tasks.

The host owns authorization, microphone consent, task dispatch, reconciliation,
and explicit task cancellation. Transport adapters must implement prompt stop,
drain local audio buffers, bounded operations, and reliable playback events.
Provider/tool deadlines remain the backend's responsibility. Shutdown stops
speech immediately and awaits already started backend work; it never invokes
M2 cancellation. A slow injected backend can delay shutdown completion.

## Transcripts, delivery, and interruptions

- `speech_started` stops current output; `speech_stopped` ends active input.
  Pause disables listening and output; resume resynchronizes context.
- Partial/final transcript events retain raw text, normalized whitespace, final
  status, and revision in a scoped SQLite ledger. Partials never trigger tools.
  Stale/duplicate finals cannot submit twice. Conflicting same-revision text is
  rejected. Revised finals after dispatch annotate the original user turn as a
  correction requiring effect review; they never repeat already executed tools.
- Generated output is stored separately in `voice_delivery`, atomically with
  a conversation exchange marked unheard. Playback events contain a monotonic
  character-prefix count, supplied by the player, rather than inferred from
  elapsed time or model transcript timestamps.
- Only acknowledged text enters assistant history as spoken. Unplayed suffixes
  remain marked unheard and are excluded from subsequent context and automatic
  summaries. Played output establishes device delivery, not proof of human
  attention. Summaries produced before acknowledgment conservatively retain
  the unheard marker; they are not retroactively regenerated.
- Interruption, pause, disconnect, and shutdown freeze delivery. Late player
  acknowledgments and stale epochs cannot revive it. Backend work keeps running;
  a late response is durably saved as unheard and never unexpectedly spoken.
- Reconnect resends current scoped history, commitments, and durable task state;
  it does not replay generated output. The host can call `synchronize()` after
  task reconciliation. Policies remain enforced/refreshed by the backend, not
  by transport-supplied instructions.
- Restart freezes unfinished playback. A request left generating is marked
  `uncertain_restart` and never automatically repeated, since tools might have
  run before the process stopped. The host must review uncertain or failed
  requests before issuing a distinct new utterance ID.

`TaskOrchestrator.conversation_state` reports original scoped receipts, lifecycle
state, evidence, errors, and revalidation flags; service prose stays labeled
untrusted. Returned results containing errors, incomplete results, missing
results, and success strings without artifacts/validation are reported failed.
This is returned evidence, not independent proof that a real task ran.

## macOS fallback

`MacOSSpeechTransport(confirm_audio=True)` explicitly enables local speech.
It uses `/usr/bin/say` with text through stdin and no shell; input is supplied as
text events. It implements no microphone capture or speech recognition. Stop
terminates the process, with a bounded wait and kill fallback. Only clean process
completion acknowledges the full output. On interruption it cannot identify
word boundaries, so the entire unconfirmed portion stays unheard. A successful
process exit does not detect mute/device failure or prove a person heard speech.

Subprocess behavior is tested with an injected fake process. No actual `say`
process, microphone capture, or audio-device evaluation was run in this milestone.

## Live adapter and opt-in evaluation

Official [GPT-Live client delegation documentation](https://developers.openai.com/api/docs/guides/live-delegation)
was checked on 2026-10-11. Client delegation keeps application context and task
state with the backend. A future adapter must build requests from saved
application transcripts/state, rather than assume a delegation event contains
full task text. It must translate the semantic transport contract to the actual
Live protocol and send concise verified speaking briefs. The protocol's append
limits and paraphrased speech require real output/player reconciliation; backend
answer length is not evidence of Live speech playback.

Direct `OPENAI_API_KEY` is absent in local settings. No account capability probe
or live voice request was made. OpenRouter credentials do not authenticate direct
OpenAI voice. There is no GPT-Live adapter, permanent cloud TTS choice, or live
microphone adapter in this milestone.

`sadaf.voice_evaluation.evaluate` is an adapter-neutral opt-in host hook. Supply
a measured runner and explicit candidate IDs. `confirm_live=True` is required
before any runner call; microphone runs additionally require
`microphone=True, confirm_microphone=True`. The host runner must enforce those
choices in its capture/provider implementation; this hook does not open devices.
Use the same bundled synthetic names/numbers, language-switch, and interruption
cases for every candidate. Expand the case set before a production evaluation.

Record useful-answer latency from completed input to first useful played answer,
interruption recovery from stop intent to recovered playback, exact recognition
targets, connected duration, and separate voice/backend costs. `Observation`
accepts measured values; costs may be unavailable or explicitly labeled estimates.
Do not store personal recordings or transcripts in development state. No live
measurements or model ranking exist yet; injected fake observations test the
measurement plumbing only.

## Offline verification

Run `.venv/bin/python -m pytest -q tests_offline/test_voice.py
 tests_offline/test_voice_integration.py` (on one shell line), or the default
full suite. The integrated fixture uses temporary databases and local Markdown:
confirmed memory → two concurrent fake tasks under A → interrupted speech →
correction → project B isolation → restart → A results with original revisions,
retained policies, no duplicate submission, and one evidence-backed fake success
versus one unverifiable failure. Separate cases cover provider/policy failure,
uncertain restart, transcript revisions, conservative summaries, reconnect,
shutdown during reasoning, local speech process behavior, and opt-in gates.
These are simulated scenarios, not live provider or M2 execution results.
