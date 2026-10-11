# Session log

Append new entries in date order. Preserve earlier entries; corrections should
be explicitly noted in a later entry.

## 2026-10-11 — Persistent development state

- Created `.project-state/` with status, roadmap, decisions, handoff, this log,
  and the initial dirty-checkout inventory.
- Added root repository instructions for resuming and recording progress.
- Linked existing implementation planning to the canonical status record.
- Verified local Markdown links, six prompt blocks, and Git ignore behavior.
- Broad diff check found whitespace issues in earlier application edits; focused
  checks on state documents passed. Earlier edits were preserved.
- Application code, runtime memories, credentials, and provider behavior untouched.
- Commit: none. Next: milestone 1, offline foundation.

## 2026-10-11 — Milestone 1 offline foundation

- Added CPython 3.13.3 setup with `uv.lock`; optional provider, audio, and
  vector dependency groups; and placeholder-only `.env.example`.
- Added explicit role settings, dotenv and environment precedence, validated
  M2 URL and data paths, redacted key fields, and Google SDK correction.
- Added side-effect-free offline doctor and fake text path with injected
  provider/store interfaces. Legacy `main.py` remains in place.
- Scoped default pytest to `tests_offline/` to avoid the legacy live-client
  fixture. Added offline tests and legacy memory hazard documentation.
- Verification: locked offline sync passed; 38 tests passed; doctor and
  synthetic text command passed; no live providers or real memories accessed.
- Implementation commit: `b1eeb43bfa7b8cbbac99dba8bcb6164377d60085`.
- Next: milestone 2 SQLite memory and safe synthetic-fixture migration.

## 2026-10-11 — Milestone 2 scoped SQLite memory

- Implemented the `MemoryRepository` contract and SQLite store for episodes,
  facts, edges, revisions, extraction jobs, and forgotten-value tombstones.
- Added evidence links and scoped recall; user profile Markdown is per-user,
  assistant persona is separate, and explicit preference overrides take priority.
- Added provisional conflict handling, explicit correction/expiry, lexical FTS,
  validated extraction patches, stale-job recovery, and complete key forgetting
  that purges revision values/index entries/edges and cancels queued extraction.
- Replaced legacy migration with dry-run default, explicit apply, configured
  path guard, SQLite backup, and idempotent fixture imports.
- Verification: offline lock sync, compileall, doctor, fake text, and 66 tests
  passed. Synthetic fixtures only; live providers and real memories untouched.
- Implementation commit: `fd5fa2672d62c2cbf79a48aa77fc5228408c98ff`.
- Next: milestone 3 local project Markdown, policy authority, revisions, and isolation.

## 2026-10-11 — Milestone 3 local project context

- Confirmed milestone 2 implementation commit exists:
  `fd5fa2672d62c2cbf79a48aa77fc5228408c98ff`. Preserved earlier dirty files.
- Added user-scoped durable registration/active selection, explicit root grants,
  repository references, shared organization policies, and seven packaged templates.
- Added local historical revision reads/CAS, full mandatory policy loading,
  keyed conflict/budget checks, owner amendment workflow, preference overlays,
  selective project knowledge/untrusted sections, snapshots, and revalidation flags.
- Offline verification: 84 tests passed; compileall, locked sync, doctor, fake
  text mode, wheel build, and temporary wheel template initialization passed.
  Packaging probe exposed and fixed resource loading before final verification.
- Tests used temporary projects, databases, and an opaque-revision fake. No cloud
  API invented, no provider/voice/M2 run, no real-memory read or migration.
- Limits: prose conflicts need review, local CAS is cooperative, snapshots are
  optimistic, host authenticates owners, and orchestration must act on flags.
- Implementation commit: `578282502bc7ff81bbacb24107cbe2fd80a6ccc3`.
- Next: milestone 4 typed conversation context, provider/tool normalization,
  thread continuity; integrate project preparation blockers with fakes first.

## 2026-10-11 — Milestone 4 conversation backend

- Confirmed milestones 1–3 and preserved all pre-existing dirty paths.
- Added typed/budgeted context assembly, a restart-safe scoped SQLite thread store,
  exact turns, separate durable summaries/commitments, optional threshold-based
  summarization, memory evidence adaptation, project policy refresh, and thread
  project pinning.
- Added the stateless OpenRouter Chat Completions adapter for configurable GPT-6.1
  Sol / GPT-6 Luna roles: normalized responses, tools, streaming/usage, bounded
  retries and optional declared fallback. Added schema-validated structured tool
  observations, lazy legacy signature translation, blocking-call offload, and
  camera confirmation enforcement.
- Added one-request `live-smoke --confirm-live` with fixed synthetic text; it was
  not run. OpenRouter official docs and model pages were checked. No provider
  generation or account access was tested.
- Verification: 103 offline tests passed; compileall, locked offline sync, doctor,
  fake text, and wheel build passed. Live smoke without the explicit flag exited
  before network access. `git diff --cached --check` passed for eight explicit
  milestone files.
- Limitations: no legacy voice or M2 wiring; actual M2 contract absent; summary
  generation is opt-in; unknown model capabilities need declaration; legacy tool
  dependencies remain optional and timed-out worker side effects cannot be killed.
  No real memory was opened or migrated.
- Implementation commit: `d6490961a3fb1c6921f9ac06316011f23bb74a2b`.
- Next: milestone 5 typed M2 request and receipt lifecycle with a fake; do not
  invent the M2 service API.

## 2026-10-11 — Commit earlier baseline work

- Reviewed the original `EXISTING_WORK.md` inventory and committed 27 explicitly
  selected tracked and new source files for the earlier V7/provider integration.
  Recorded it as work-in-progress, not as completion of an implementation
  milestone. Applied whitespace-only cleanup to the selected source files.
- Verification: 103 offline tests passed; compileall passed for the selected
  changed/new Python files; staged whitespace check passed. No app startup, live
  provider call, voice capture, or legacy memory access was performed.
- Excluded `.m2_cache/` databases, repair/review drafts, and `test_deepseek.py`,
  whose body makes live provider calls and constructs the legacy memory store.
- Commit: `944ceb853a6cfe5e64e5d82c81077776ab94dd31`.
- Next remains milestone 5; use fake M2 operations until its actual contract is
  supplied.

## 2026-10-11 — Milestone 5 M2 task lifecycle

- Confirmed milestone 4 (`d6490961...`) and earlier WIP commits exist; kept all
  pre-existing untracked cache, repair/review notes, and live-test script out of
  the change. No M2 repository/API contract was present in tracked sources.
- Added `sadaf.tasks` with typed task requests and policy revisions, a semantic
  client protocol, deterministic fake, transactional SQLite receipts/events,
  idempotency, restart reconciliation, bounded concurrency, same-checkout
  serialization, dependency gating, cancellation transitions, pinned project
  attribution, and revalidation flags. Success requires a returned complete
  result with artifacts or validation evidence; partial and unverifiable results
  remain failures with evidence retained.
- Added `docs/M2_TASKS.md` describing the interface and limits.
- Verification: locked offline sync passed; compileall passed; 113 offline
  tests passed (including 10 task lifecycle cases); doctor and fake text mode
  passed; offline wheel build passed. No M2 endpoint, provider, real memory, or
  legacy memory store was accessed. `test_deepseek.py` was not run.
- Limit: a future real adapter must map the supplied M2 contract and honor
  idempotency across the submit/save crash window; the local fake does not test
  remote delivery or actual task execution.
- Implementation commit: `cf8ef41b5c7071546d2ad0cf31e77d4204152ab9`.
- Next: milestone 6 voice transport and integrated offline evaluation, keeping
  microphone/provider evaluation opt-in and separately recorded.


## 2026-10-11 — Milestone 6 voice and integrated offline evaluation

- Read canonical state, Session 6, and revival plan; confirmed milestone 5
  `cf8ef41b5c7071546d2ad0cf31e77d4204152ab9` exists. Preserved all four existing
  untracked paths and local databases. No legacy memory was read/migrated and
  `test_deepseek.py` was not run.
- Added replaceable voice transport/controller, deterministic fake, macOS speech
  fallback, transcript reconciliation/deduplication, durable generated/played
  ledger, interruption/stop, context synchronization, reconnect, and shutdown.
  Unheard speech stays excluded from completed history and summaries. Pausing
  voice leaves coding tasks active; uncertain restart requests do not replay.
- Added fresh scoped task context and rejected success-with-errors results.
  Added opt-in candidate evaluation hook with recognition/latency/recovery/cost
  observation fields and identical synthetic cases. Actual live adapters remain
  pending; fake measurements are not live results.
- Integrated fixture exercises memory correction, A/B switching/isolation,
  full policy retention, concurrent fake M2 tasks, interrupted speech, restart,
  original policy/task attribution, no duplicate submission, and evidence-based
  success versus unverifiable failure.
- Verification: 127 offline tests passed; compileall, locked offline sync,
  doctor, fake text, offline wheel build, and focused whitespace check passed.
  No provider/M2 request, microphone, actual audio process, or real memory use.
- Checked official OpenAI client-delegation documentation. Direct OpenAI key is
  absent; account access is unverified. No live evaluation or winner claimed.
- Implementation commit: `6f83d1c` (`Implement offline voice transport lifecycle`).
- Next: supplied real M2 contract or consented Live/player adapter, contract
  validation and explicit synthetic live evaluation, then application wiring.
