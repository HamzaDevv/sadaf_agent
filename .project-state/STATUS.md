# Implementation status

Updated: 2026-10-11 (Asia/Kolkata).

## Provider cost update (2026-10-11)

- Changed active legacy application default from Groq to OpenRouter. Reasoning,
  chat, agent, and vision model roles now use DeepSeek V4.1 Flash `:floor`
  (lowest-priced provider routing); speech transcription uses Qwen3 ASR 0.6B.
- The continuous listener now sends completed audio through the configured
  proxy instead of constructing a Groq client directly.
- Added an explicit `SADAF_VOICE_PROVIDER=openrouter` path for Qwen Audio 3.0
  TTS Flash. It writes a temporary MP3 for macOS playback and deletes it after
  playback. Default remains local `say`, so no provider TTS cost is incurred.
- Standalone role settings remain fake by default; selecting OpenRouter uses
  the same DeepSeek model for reasoning and extraction. Voice remains disabled
  there unless explicitly selected.
- Offline validation: 133 tests passed after adding the Qwen ASR JSON adapter and
  fake request tests; targeted compileall and focused `git diff --check` passed.
- Live synthetic validation: DeepSeek returned the exact requested check phrase
  (50 input/45 output tokens); Qwen TTS returned MP3 audio for two short phrases;
  Qwen ASR transcribed `The synthetic reference code is Kilo Seven.` from
  generated audio (3.408 s audio, reported cost $0.00001134864). Estimated total
  from reported usage and catalog TTS rates is about $0.00125, below the user's
  $0.15 cap. Malformed fixture requests returned 400 without usage data; their
  billing status is not exposed in the response. No microphone was used and
  generated TTS audio was not played.
- Catalog rates and capabilities are volatile and not quality-tested. `:floor`
  is price-first and can trade availability/latency. See the cost update in
  `docs/REVIVAL_PLAN.md` and decision D017.
- This change is not committed yet. Earlier untracked files and databases remain
  untouched.

## Current position

Milestones 1–6 are implemented offline. M2 and voice use fakes because no M2
contract or direct OpenAI voice credentials are available. A replaceable voice
controller now wraps the new conversation backend. The legacy application path
has provider configuration and listener/speaker adapter changes, but its
conversation flow is still separate from that controller. Real legacy memory
remains untouched. Live evaluation is pending.

Milestone 3 implementation commit: `578282502bc7ff81bbacb24107cbe2fd80a6ccc3`.

## Completed

- Repository instructions direct future sessions to this folder.
- Persistent roadmap, decisions, session log, next-step handoff, and prior-work
  inventory are established.
- Existing research and sequential prompts reference this canonical status.
- Earlier session stored `OPENROUTER_API_KEY` in ignored `.env` and confirmed
  read-only authentication. No generation or voice capability was tested.
- Added a CPython 3.13.3 setup (`pyproject.toml`, `uv.lock`) with provider,
  audio, and vector extras separated from default offline installs.
- Added role-based validated settings with explicit dotenv loading, process
  environment precedence, credential redaction, M2 URL validation, and data
  path boundaries that guard legacy memories and symlinks.
- Added `sadaf doctor` and ephemeral fake text mode using injected provider and
  turn-store interfaces. Imports and commands open no client or persistent
  store; fake results are labeled and live capability is not claimed.
- Corrected the Google package mismatch to `google-genai`; documented legacy
  graph read/prune and migration hazards in `docs/OFFLINE_SETUP.md`.
- Default pytest collection is scoped to `tests_offline/`; the suite blocks
  network connections and verifies settings, injection, CLI redaction/imports,
  and unchanged synthetic legacy data.
- Added `MemoryRepository` with transactional SQLite episodes, scoped facts,
  relationship edges, revision history, and an extraction outbox.
- Facts retain turn/episode evidence, confirmation status, sensitivity/export
  permissions, durability, and effective/expiry timestamps. Explicit profile
  preferences are per-user Markdown sources and override extracted preference
  facts; the assistant persona remains a separate editable file.
- Added side-effect-free lexical recall using rebuildable SQLite FTS. Explicit
  correction supersedes conflicting facts, expiry is a deliberate lifecycle
  operation, and forgetting a key removes all its values, revisions, edges,
  and index rows while cancelling and clearing queued extraction payloads.
- Added validated extraction patches, job failure/no-fact distinction, and
  recovery of stale processing jobs. SQLite writes do not depend on embeddings.
- Replaced the legacy migration script with a dry-run-first importer for copied
  graph/archive/episode fixtures. Apply is explicit, protects the configured
  legacy path, backs up an existing SQLite target, and records idempotent imports.
- Added synthetic fixture tests for concurrent writes, restart recall, evidence,
  correction, expiry, forgetting, user/project isolation, outbox lifecycle,
  backup, repeat import, and the migration CLI.

- Added durable user-scoped project registration, authorized/nonoverlapping roots,
  repository references, shared organization policy registration, and per-thread
  active-project state. Activation verifies context before changing selection.
- Added seven packaged Markdown templates and a document-source protocol with
  a local SHA-256 revision archive, historical reads, and conditional updates.
- Added deterministic full policy loading, keyed conflict checks, reserved policy
  character budget, explicit owner-authorized document amendments, project style
  overlays, and separate knowledge/untrusted section retrieval.
- Added fresh manifest snapshots before preparation, fail-closed stale/unavailable
  policy handling, and original-project revalidation flags after policy or context
  edits. Local source/root mismatches and path/symlink escapes are rejected.
- Added temporary-project tests and an opaque-revision fake for service conflicts,
  concurrent local writers, external edits, restarts, isolation, and policy outages.

- Added `sadaf.conversation`: typed, explicitly budgeted context packets; scoped
  durable SQLite thread turns, project pinning, durable summaries and commitments;
  injected memory and project-context adapters; and an optional threshold-driven
  summarizer that does not add a model call on every turn.
- Added an OpenRouter Chat Completions client with normalized text/tool calls,
  usage and streaming events; configurable model settings with GPT-6.1 Sol and
  GPT-6 Luna defaults; bounded retries, optional declared fallback, and capability
  checks. It sends no provider-managed conversation state or generic model params.
- Added validated structured tool observations, bounded tool loops, lazy legacy
  tool signature adapters, worker-thread handling for blocking tools, and a hard
  camera confirmation gate. The adapter is opt-in and imports handlers on use.
- Added `sadaf live-smoke --confirm-live`, which can send one fixed synthetic
  request. No live request was made in this session.

## Verification

- State Markdown files and all local Markdown links checked for existence.
- Six implementation prompt blocks retained.
- `.env` remains ignored; state files are not ignored.
- `UV_CACHE_DIR=/tmp/sadaf-uv-cache uv sync --locked --offline` completed.
- `.venv/bin/python -m pytest -q`: 38 passed, no warnings.
- `.venv/bin/python -m sadaf doctor`, `.venv/bin/python -m sadaf text --message
  'Synthetic setup probe'`, and installed `sadaf --no-dotenv doctor` passed.
- Subprocess checks confirmed forbidden legacy/provider imports and network
  attempts fail, and a synthetic legacy graph fixture remained byte- and
  timestamp-identical. `.env` remains ignored and no key was printed.
- Focused `git diff --check` for milestone files passed. Whole-checkout
  whitespace problems remain in pre-existing application edits; those files
  were left untouched.
- Offline-only validation; no provider, voice, vector, M2, or real-memory
  integration was exercised.
- `.venv/bin/python -m compileall -q sadaf scripts/migrate_memory.py tests_offline`
  passed.
- `.venv/bin/python -m pytest -q`: 66 passed.
- Doctor, fake text mode, and `UV_CACHE_DIR=/tmp/sadaf-uv-cache uv sync --locked --offline` passed again.
- Focused `git diff --check` for milestone 2 files passed. Tests used temporary
  synthetic databases and copied JSON fixtures only.

## Milestone 3 verification

- `.venv/bin/python -m pytest -q`: 84 passed (18 new project-context cases).
- `.venv/bin/python -m compileall -q sadaf tests_offline` passed.
- `UV_CACHE_DIR=/tmp/sadaf-uv-cache uv sync --locked --offline` passed.
- `.venv/bin/python -m sadaf --no-dotenv doctor` and fake text mode with a
  synthetic message passed; no clients or persistent stores were started.
- `UV_CACHE_DIR=/tmp/sadaf-uv-cache uv build --wheel --offline --out-dir
  /tmp/sadaf-m3-wheel` passed without warnings after fixing resource loading.
  A temporary subprocess loaded the wheel and initialized all seven templates.
- Focused `git diff --check` passed. Explicit staging includes only milestone 3
  code, templates, tests, documentation, packaging, and canonical state.
- Temporary directories, synthetic content, and fakes only. No cloud/M2 API,
  live provider, voice, real legacy-memory read, or migration was exercised.

## Dependencies and limitations

- Real M2 integration needs its repository or API contract; use a fake meanwhile.
- Direct OpenAI voice needs separate credentials/access; OpenRouter auth does
  not establish voice access.
- Model recommendations are research candidates, not evaluation winners;
  recheck capabilities before integration.
- Legacy memory reads may prune data. Protect real memory throughout development.
- Checkout contains substantial earlier unfinished work; see `EXISTING_WORK.md`.
- Milestone 1 commit: `b1eeb43bfa7b8cbbac99dba8bcb6164377d60085`.
- Milestone 2 commit: `fd5fa2672d62c2cbf79a48aa77fc5228408c98ff`.
- Vector indexing, live extraction providers, and wiring the new store into the
  legacy voice/application loop remain future work; no live integrations were
  claimed.
- Fact forgetting leaves its source episode as separate evidence; episode-level
  deletion or redaction is not implemented. The SQLite adapter is not yet wired
  into the legacy conversation loop, and Markdown-only memory exports are not
  imported by the JSON fixture importer.

- Milestone 3 is a standalone offline library (`sadaf/projects.py`), not a legacy
  loop integration, running-task engine, cloud adapter, or M2 dispatcher.
- Policy conflicts are detected for explicit keyed MUST rules; prose semantic
  consistency needs owner review. Policy budget measures characters, not tokens.
- Local conditional writes serialize cooperating Unix/macOS writers. External
  editors ignoring the lock can race the final replace; cross-source snapshots
  are optimistic, not distributed transactions.
- Owner/actor authentication and source grants belong to the trusted application.
  Revisions archive observed content; actor/reason audit history and archive
  retention management are future work. Templates do not establish owner review.
- Revalidation flags are now durable on task receipts; a host must pause/review
  affected running work before continuing under changed policy.

## Milestone 4 verification and limits

- `.venv/bin/python -m pytest -q`: 103 passed.
- `.venv/bin/python -m compileall -q sadaf tests_offline` passed.
- `UV_CACHE_DIR=/tmp/sadaf-uv-cache uv sync --locked --offline` passed.
- `sadaf --no-dotenv doctor` and fake text mode passed. `live-smoke` without
  `--confirm-live` exited 2 before making a request.
- Offline wheel build passed. Staged `git diff --check` passed; stage contained
  only eight milestone 4 files. All checks used local fixtures/fakes.
- OpenRouter Chat Completions, tool calling, GPT-6.1 Sol and GPT-6 Luna model
  details were checked against current OpenRouter documentation/catalog pages.
  No live generation or account capability was tested.
- Commit: `d6490961a3fb1c6921f9ac06316011f23bb74a2b`.
- This remains a standalone text backend, not connected to the legacy voice loop
  or M2. OpenRouter key/access and provider routing are unverified. Unknown
  model capabilities require explicit declaration. Summary generation is
  optional and threshold-driven; it is not automatic unless the host injects a
  summarizer. Legacy tool modules are lazy and some optional dependencies may be
  unavailable; timed-out worker-thread side effects cannot be forcibly stopped.
- No real memory was read or migrated. No cloud or M2 interface was invented.

## Milestone 5 verification and limits

- Added typed task requests and policy revision pins, a semantic `M2Client`
  protocol, and `FakeM2Client`; no service endpoint or wire contract was added.
- Added transactional SQLite request snapshots, receipts, and lifecycle events;
  idempotent submit, dependency gating, bounded concurrency, same-checkout
  serialization, restart reconciliation, cancellation states, original scope,
  and durable revalidation flags.
- Results are reported successful only when retrievable, complete, and backed by
  artifacts or validation evidence. Partial results and success responses
  without evidence are persisted as failures.
- `.venv/bin/python -m pytest -q`: 113 passed, including 10 task lifecycle cases.
  Compileall, locked offline sync, doctor, fake text mode, and offline wheel
  build passed. All lifecycle tests use temporary databases and the fake.
- Milestone commit: `cf8ef41b5c7071546d2ad0cf31e77d4204152ab9`. No M2, provider, or
  legacy memory service was contacted; `test_deepseek.py` was not run.
- A future adapter must map a supplied M2 contract and honor idempotency across
  the remote-submit/local-save crash window. The fake cannot verify remote
  delivery or task execution. Revalidation flags are recorded; host policy
  orchestration still must act on them.

## Milestone 6 verification and limits

- Added `sadaf.voice`: replaceable semantic transport, fake event queue, explicitly
  enabled macOS `say` fallback, listening/transcript revisions, interruption,
  playback stop, context synchronization, bounded reconnect, and graceful shutdown.
- Added scoped raw/cleaned transcript and durable delivery ledgers. Generated
  speech starts unheard; only acknowledged prefixes enter conversation history
  and summaries. Late/stale acknowledgments cannot revive interrupted output.
  Revised finals annotate corrections without repeating tools. Uncertain restart
  requests require review rather than automatic replay.
- Backend work continues while paused/interrupted; M2 cancellation is separate.
  Task-context injection refreshes scoped receipts. Results containing errors are
  now failed even when some validation evidence exists.
- Integrated temporary-fixture scenario covers confirmed memory/correction,
  project A/B isolation, full policy retention, two concurrent fake M2 tasks,
  interruption, restart, original policy pins, deduplication, and truthful states.
- Added opt-in evaluation hook with identical synthetic candidate cases and
  latency, interruption recovery, recognition, duration, and cost observations.
  Tests exercise gates/measurement plumbing only; no candidate winner is claimed.
- `.venv/bin/python -m pytest -q`: 127 passed. Compileall, locked offline sync,
  doctor, fake text, and offline wheel build passed. Focused whitespace check
  passed. No microphone, actual `say`, provider, M2, or real legacy memory was used.
- Official OpenAI client-delegation documentation checked; direct OpenAI key is
  absent in settings. There is no Live or microphone adapter and no live access,
  latency, recognition, or cost result. macOS process behavior uses an injected
  fake in tests; interrupted speech has no known word boundary and conservatively
  stays unconfirmed. Clean `say` exit establishes process completion, not human
  hearing or audio-device health.
- Standalone new backend path only; host owns session exclusivity, bounded
  transport operations/provider deadlines, task reconciliation/revalidation, and
  review of uncertain effects. Shutdown awaits already-started backend work.
- Implementation commit: `6f83d1c` (`Implement offline voice transport lifecycle`).

## Next concrete step

Supply the real M2 contract and/or direct voice credentials and a consented
microphone/player adapter. Validate that adapter against the transport contract,
then explicitly opt into synthetic live evaluation. Before real data use, plan
application wiring and review uncertain-request recovery; do not open/migrate
legacy memories without a separate request.

## Earlier baseline application work commit

- After the milestone commits, committed 27 explicitly selected earlier
  application/provider source files from the original dirty-checkout inventory:
  V7 orchestration, provider adapters, memory/tool/audio changes, and context
  generation tooling. This is preserved work-in-progress, not a newly completed
  milestone, and no live behavior is claimed.
- Verification: `.venv/bin/python -m pytest -q` passed (103 tests);
  `compileall` passed for the selected changed/new Python sources; staged
  `git diff --cached --check` passed. No app startup, provider request, voice
  capture, or legacy memory operation was run.
- Commit: `944ceb853a6cfe5e64e5d82c81077776ab94dd31`.
- Left `.m2_cache/`, `repair/` and review text, and `test_deepseek.py` uncommitted.
  The test script calls live providers and opens the legacy memory store; do not
  run it as an offline check. Local cache databases and draft notes are not code.
