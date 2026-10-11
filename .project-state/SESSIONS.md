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
- Implementation commit: recorded in the follow-up handoff commit.
- Next: milestone 4 typed conversation context, provider/tool normalization,
  thread continuity; integrate project preparation blockers with fakes first.
