# Implementation status

Updated: 2026-10-11 (Asia/Kolkata).

## Current position

Milestones 1–3 are implemented and committed; milestone 3 is verified offline. The existing voice loop and
legacy memory store have not been replaced, started, or migrated during this
session. Milestones 4–6 remain pending.

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

## Next milestone

Milestone 4: conversation backend, OpenRouter adapter, normalized tools,
thread continuity, and typed context packets. Use Session 4 in
`docs/IMPLEMENTATION_PROMPTS.md`; first test with injected fakes. Integrate the
project layer's preparation blockers and scoped snapshots into that backend.

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
- Revalidation flags require future orchestration to pause/review changed policies.
