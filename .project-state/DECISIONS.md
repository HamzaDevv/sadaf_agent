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

## D010 — Explicit project and policy capabilities

Accepted: 2026-10-11. A durable user-scoped registry grants nonoverlapping local
context roots and records repository references, owners, and shared organization
policy attachments. Active selection is per user/thread; task preparation takes
an explicit original project ID. File text cannot change authority. Required
organization/project policies are retained in full, keyed conflicts and budget
overflow block, working style overlays global preferences, and other source text
stays knowledge or untrusted content. Prose conflicts need human review.

## D011 — Optimistic revisioned local documents

Accepted: 2026-10-11. Use a document-source protocol, SHA-256 local manifests,
observed revision archives, and double-collect snapshots. Preparation refreshes
required policies and never falls back to stale or empty context. Explicit owner
amendments require expected revisions and a reason; actor authentication is the
host's responsibility. Local advisory locking protects cooperating writers,
not arbitrary external editors; multi-source snapshots are optimistic. Existing
tasks retain original scope and receive revalidation flags for changed policy or
context. Actual task lifecycle reactions belong to milestone 5. No cloud wire
protocol or M2 endpoint is assumed; offline tests use an opaque-revision fake.

Milestone 3 implementation: `578282502bc7ff81bbacb24107cbe2fd80a6ccc3` (offline only).

## D012 — Stateless OpenRouter Chat Completions adapter

Accepted: 2026-10-11. Use OpenRouter's documented Chat Completions endpoint for
the first text backend. Keep history, summaries, and project snapshots locally;
do not send provider-managed conversation state or generic model parameters.
Normalize text, tool calls, streaming events, usage, and provider errors. Start
with `openai/gpt-6.1-sol` for reasoning and `openai/gpt-6-luna` for extraction,
but keep role model IDs configurable and live access unverified. Bound retries;
fall back only to an explicitly configured model.

## D013 — Typed, budgeted conversation context and continuity

Accepted: 2026-10-11. Build context as separate bounded sections and reserve the
full policy allocation; fail when binding rules do not fit. Keep exact turns,
thread summaries, and commitments as distinct durable records. Summaries are
unverified and are generated only through an optional threshold-based host
summarizer. Threads pin their project, and project rules are refreshed before
each turn. Tool specifications are validated and injected; camera calls require
explicit host confirmation. The standalone backend does not itself connect the
legacy voice loop or dispatch M2 tasks.

Milestone 4 implementation: `d6490961a3fb1c6921f9ac06316011f23bb74a2b` (offline only).
