# Implementation status

Updated: 2026-10-11 (Asia/Kolkata).

## Current position

Milestones 1 and 2 are implemented and committed. The existing voice loop and
legacy memory store have not been replaced, started, or migrated during this
session. Milestones 3–6 remain pending.

Implementation commit: `b1eeb43bfa7b8cbbac99dba8bcb6164377d60085`.

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

## Next milestone

Milestone 3: local Markdown project context, policy authority, revision
snapshots, and project isolation. Use Session 3 in
`docs/IMPLEMENTATION_PROMPTS.md`. Keep using temporary directories and fakes;
the real legacy memory directory remains untouched.

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
