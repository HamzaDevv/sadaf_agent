# Persistent development state

This folder is the version-controlled handoff for building Sadaf across coding
sessions. It stores development progress, not Sadaf's runtime personal memory
or an assistant's hidden reasoning. Future sessions must still inspect the
actual files and Git status; these notes can become stale.

## Start a session

1. Read `STATUS.md` and `HANDOFF.md`.
2. Inspect Git status and applicable repository instructions.
3. Consult `ROADMAP.md`, `DECISIONS.md`, and the linked implementation prompt.
4. Continue the next unfinished milestone unless the user changes direction.

## Files and ownership

| File | Purpose |
| --- | --- |
| `STATUS.md` | Current implementation state and verification; canonical progress record. |
| `HANDOFF.md` | Next action, relevant context, and unresolved dependencies. |
| `ROADMAP.md` | Milestones and completion criteria. |
| `DECISIONS.md` | Accepted direction, rationale, and provisional choices. |
| `SESSIONS.md` | Append-only record of completed sessions. |
| `EXISTING_WORK.md` | Initial dirty-checkout inventory for preserving prior work. |

`docs/REVIVAL_PLAN.md` contains the design research; `docs/IMPLEMENTATION_PROMPTS.md`
contains the sequential prompts. `docs/IMPLEMENTATION_STATUS.md` points here,
rather than maintaining a competing progress record.

## End a session

Update status and handoff together. Record the date, completed work, exact
verification commands/results, remaining limitations, and commit hash when
one exists. Append a session entry; do not overwrite earlier entries. Record
architecture decisions with their status and rationale. Keep planned work
distinct from completed work, and offline verification distinct from live tests.

Keep notes concise and safe to commit. Never copy API keys, `.env` contents,
private profile values, or raw user transcripts here. Refer to configuration
variable names or file paths instead. Run sessions sequentially in this checkout;
this Markdown handoff does not provide locking for concurrent writers.
