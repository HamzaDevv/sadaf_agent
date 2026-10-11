# Next-session handoff

Updated: 2026-10-11 (Asia/Kolkata).

## Resume here

Milestones 1–5 are implemented and committed offline. Milestone 5 adds typed M2
requests, durable receipts/events, and a fake lifecycle in `../sadaf/tasks.py`.
No M2 repository/API contract was found, so there is no real adapter or invented
endpoint. Next implement milestone 6 using Session 6 in
`../docs/IMPLEMENTATION_PROMPTS.md`.

Before continuing, inspect `git status` and preserve unrelated edits. The existing
voice loop and legacy memory store remain untouched by the new conversation path.
Do not push. Stage only explicit milestone files.

Earlier baseline V7/provider source work is now committed as work-in-progress:
`944ceb853a6cfe5e64e5d82c81077776ab94dd31`. It is not a completed milestone and
was not live-tested. Remaining untracked `.m2_cache/`, `repair/`, review notes,
and `test_deepseek.py` were intentionally left out. Do not run
`test_deepseek.py`: it makes live provider calls and opens the legacy memory store.

## Milestone 4 interfaces

- `../sadaf/conversation.py`: typed context assembly, thread store, provider and
  tool protocols, OpenRouter adapter, memory adapter, project loader, and legacy
  tool compatibility adapter.
- `../docs/CONVERSATION_BACKEND.md`: construction, authority boundaries, live
  smoke command, and limitations.
- `../tests_offline/test_conversation.py`: SQLite thread restart/compaction,
  provider normalization/retry/stream, tool validation/timeout boundaries,
  camera gate, memory evidence, and loop exhaustion fixtures.
- `ProjectContextLoader` refreshes full binding policy text plus selected project
  sections on each turn. Project policy conflicts or missing/stale required
  context block the turn. Threads retain their original project; project change
  requires a new thread ID.
- The optional summarizer runs only after a configured threshold and persists a
  summary clearly labeled unverified. Exact recent turns remain stored. The host
  decides when and how to summarize and whether summaries need review.
- `sadaf live-smoke --confirm-live` sends one fixed synthetic request only when
  explicitly run. It was not run during milestone 4.

## Verification and limitations

- 103 offline tests passed; compileall, locked offline sync, doctor, fake text,
  and offline wheel build passed. `live-smoke` without confirmation exited 2
  before network access. No live request was made.
- Current OpenRouter Chat Completions, tool calling, and model details were
  checked in official docs/catalog pages, but account access and live behavior
  remain unverified.
- The backend and task lifecycle are not wired into the legacy voice loop. A
  supplied M2 contract is still needed for a real adapter.
- Legacy tools are optional and lazy. Some dependencies may be unavailable in
  an offline install. A worker-thread timeout cannot stop an already-running
  side effect. Camera execution requires a host-supplied confirmation callback.
- Project policy prose conflicts still need owner review; project document CAS
  and snapshots retain milestone 3's cooperative/optimistic limitations.
- No real legacy memory was opened or migrated; no cloud or M2 API was invented.

## Milestone 5 interface and verification

- Implementation commit: `cf8ef41b5c7071546d2ad0cf31e77d4204152ab9`.
- `../sadaf/tasks.py`: `TaskRequest`, `PolicyRevision`, `M2Client`,
  `FakeM2Client`, `SQLiteTaskStore`, and `TaskOrchestrator`.
- `../docs/M2_TASKS.md`: protocol boundary, persistence, queueing, cancellation,
  result evidence, and fake limitations.
- Receipts retain their request's original user/project/thread, repository and
  policy revisions. Revalidation is a durable flag; the host decides whether
  changed context requires pause/review.
- Offline verification: locked sync, compileall, 113 tests, doctor, fake text,
  and wheel build passed. No provider/M2 call or real-memory access occurred.
- The fake cannot test remote delivery, server idempotency, or actual execution.
  A real adapter must honor idempotency if the process stops after remote submit
  but before saving its run ID.

## Earlier implementation commits

- Milestone 1: `b1eeb43bfa7b8cbbac99dba8bcb6164377d60085`.
- Milestone 2: `fd5fa2672d62c2cbf79a48aa77fc5228408c98ff`.
- Milestone 3: `578282502bc7ff81bbacb24107cbe2fd80a6ccc3`.
- Milestone 4: `d6490961a3fb1c6921f9ac06316011f23bb74a2b`.

## Suggested resume prompt

```text
Read AGENTS.md and .project-state/README.md, STATUS.md, and HANDOFF.md.
Continue milestone 6 using Session 6 in docs/IMPLEMENTATION_PROMPTS.md.
Preserve unrelated work, verify offline, record live evaluation separately,
update persistent state, and make a local explicit-file commit without pushing.
```
