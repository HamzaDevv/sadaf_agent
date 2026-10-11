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
