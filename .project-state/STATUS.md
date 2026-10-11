# Implementation status

Updated: 2026-10-11 (Asia/Kolkata).

## Current position

Milestone 1, the offline foundation, is implemented and committed. The existing
voice/memory application has not been replaced, started, or migrated during
this session. Milestones 2–6 remain pending.

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

## Next milestone

Milestone 2: implement SQLite global memory with provenance and safe migration.
Use Session 2 in `docs/IMPLEMENTATION_PROMPTS.md`. Work exclusively with copied
synthetic fixtures; the real legacy memory directory remains untouched.

## Dependencies and limitations

- Real M2 integration needs its repository or API contract; use a fake meanwhile.
- Direct OpenAI voice needs separate credentials/access; OpenRouter auth does
  not establish voice access.
- Model recommendations are research candidates, not evaluation winners;
  recheck capabilities before integration.
- Legacy memory reads may prune data. Protect real memory throughout development.
- Checkout contains substantial earlier unfinished work; see `EXISTING_WORK.md`.
- The milestone 1 implementation commit hash is recorded in `HANDOFF.md` and
  the session log.
