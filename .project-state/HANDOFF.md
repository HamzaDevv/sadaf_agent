# Next-session handoff

Updated: 2026-10-11 (Asia/Kolkata).

## Resume here

Milestones 1–6 are complete offline. Milestone 6 wraps the standalone conversation
backend with voice lifecycle and playback-aware history. The legacy `main.py`
voice loop and real memory store remain untouched. No live provider, microphone,
actual macOS speech process, or M2 service was exercised. Direct OpenAI voice
credentials are absent; no M2 contract is available.

Next: obtain a real M2 contract and/or a consented Live/microphone/player adapter,
validate its semantic mapping, and explicitly opt into synthetic live evaluation.
No additional live work is implicitly authorized. Application wiring, actual
recognition/playback behavior, and real task delivery remain unverified. Never
run `test_deepseek.py` as an offline check or open/migrate legacy memory to inspect
code. Preserve `.m2_cache/`, `repair/`, review notes, and local databases.

## Milestone 6 interfaces

- `../sadaf/voice.py`: `VoiceTransport`, `VoiceEvent`, `FakeVoiceTransport`,
  `MacOSSpeechTransport`, and `VoiceSession`.
- `../sadaf/conversation.py`: atomic voice exchanges, generated output ledger,
  monotonic acknowledged-prefix projection, and optional scoped task-state loader.
- `../sadaf/tasks.py`: `conversation_state` supplies durable scoped observations;
  host reconciles separately. Success with result/remote errors is now failed.
- `../sadaf/voice_evaluation.py`: explicit live/microphone gates and identical
  synthetic candidate cases with injected measurement runner.
- `../docs/VOICE_TRANSPORT.md`: construction, host boundaries, events, storage,
  macOS limitations, official delegation source, opt-in measurement procedure.
- `../tests_offline/test_voice.py` and `../tests_offline/test_voice_integration.py`:
  event lifecycle plus integrated real-library fixtures.

Voice pause, interruption, disconnect, and shutdown do not cancel M2. Backend
work completes separately; late output remains unheard. History and summaries
receive only confirmed played prefixes plus explicit unheard markers. Raw and
cleaned transcript revisions remain separate. Revised finals never repeat tools;
post-dispatch corrections flag effect review. Restart freezes pending playback
and marks unfinished requests uncertain without resubmission.

Each session pins its project; use a new thread to switch. A single host owns a
voice thread. Transport adapters must drain/stop playback, honor bounded methods,
and acknowledge actual player delivery rather than generated transcript timing.
macOS completion is a conservative process-level proxy, not proof of attention
or device health. Shutdown awaits backend jobs, so injected provider deadlines
matter. Owner authorization, policy/task revalidation orchestration, and explicit
uncertain-request review remain host responsibilities.

## Verification

- 127 offline tests passed; compileall, locked offline sync, doctor, fake text,
  offline wheel build, and focused whitespace check passed.
- Fixtures only: temporary SQLite/local Markdown, fake provider/M2/audio process.
  Integrated scenario covers correction, project switching/isolation, retained
  policies, concurrent fake tasks, interruption, restart, idempotency, original
  project/revision attribution, and success/failure evidence reporting.
- Official GPT-Live client-delegation docs checked. No direct OpenAI credential
  configured; no account capability request or live evaluation made. Evaluation
  runner and audio subprocess tests are simulated; no model ranking exists.
- Implementation commit: `6f83d1c` (`Implement offline voice transport lifecycle`). Do not push.

## Earlier implementation commits

- Milestone 1: `b1eeb43bfa7b8cbbac99dba8bcb6164377d60085`.
- Milestone 2: `fd5fa2672d62c2cbf79a48aa77fc5228408c98ff`.
- Milestone 3: `578282502bc7ff81bbacb24107cbe2fd80a6ccc3`.
- Milestone 4: `d6490961a3fb1c6921f9ac06316011f23bb74a2b`.
- Milestone 5 (confirmed in this session): `cf8ef41b5c7071546d2ad0cf31e77d4204152ab9`.
- Earlier application WIP: `944ceb853a6cfe5e64e5d82c81077776ab94dd31`.

Read `../.project-state/STATUS.md`, roadmap/decisions, and applicable repository
instructions before continuing. Stage explicit files only and commit locally.
