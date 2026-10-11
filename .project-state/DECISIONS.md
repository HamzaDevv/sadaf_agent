# Development decisions

## D001 — Version-controlled development handoff

Accepted: 2026-10-11. Keep session continuity in `.project-state/`, with
`STATUS.md` as the canonical progress record and `HANDOFF.md` as the next action.
Repository instructions make the folder discoverable. Runtime personal memory
remains separate. This supports new sessions without relying on chat history.

## D002 — Partner and execution separation

Accepted direction from the user: Sadaf manages conversation, personal context,
project constraints, and task preparation/reporting; M2 handles coding execution.
The wire protocol is pending. Use an interface and fake until it is known.

## D003 — Hybrid scoped memory

Accepted implementation direction: editable global profile and persona Markdown,
transactional SQLite facts/events/edges, and separate project policy Markdown.
Required policies load deterministically. Extracted memories retain provenance.
Implementation and migration are pending; existing personal data is untouched.

## D004 — Offline foundation first

Accepted: complete safe setup and offline tests before live providers, memory
migration, or voice integration. Preserve the dirty checkout. Make focused local
milestone commits and record their verification. Do not push by default.

## D005 — Provider choices remain provisional

OpenRouter is authorized/configured. Research model candidates and voice options
are recorded in `../docs/REVIVAL_PLAN.md`. Recheck availability and evaluate
representative scenarios before choosing permanent defaults. Cloud document
service and real M2 adapter remain undecided.

## D006 — Isolated offline foundation

Accepted: 2026-10-11. Introduce a side-effect-free `sadaf` entry point with
injected provider/store protocols and an explicitly fake, ephemeral text path.
Keep the legacy entry point intact. Default test collection excludes its
import-time live-client fixture. Offline doctor validates configuration but
does not construct clients, stores, or verify live capabilities.

## D007 — Explicit role and data boundaries

Accepted: 2026-10-11. Configure reasoning, extraction, voice, and embeddings
separately. Pin CPython 3.13 and dependency resolution; keep audio and vector
packages optional. New data defaults to ignored `.sadaf-dev/`; settings reject
paths that overlap legacy memories. Correct the Google SDK requirement to
`google-genai`, which supplies the existing `google.genai` import.

## D008 — Transactional scoped memory

Accepted: 2026-10-11. SQLite is the canonical store for episodes, facts, edges,
revisions, extraction jobs, and deletion tombstones. Every record is user
scoped and optionally project scoped. Reads are side-effect-free; SQLite FTS
is a rebuildable lexical projection. Extracted facts remain provisional and
non-exportable until an explicit application action confirms them. Explicit
profile Markdown preferences outrank extracted preferences. Vector retrieval
is optional and is not connected to canonical writes.

## D009 — Safe legacy import boundary

Accepted: 2026-10-11. Legacy import parses copied graph/archive/episode JSON
without constructing the pruning legacy store. Planning is the default; apply
requires an explicit flag, an independent target, and a backup when the target
already exists. Repeated imports of the same source content are idempotent.
Real legacy memory is not read or migrated during development.
