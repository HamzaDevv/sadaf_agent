# Next-session handoff

Updated: 2026-10-11 (Asia/Kolkata).

## Resume here

Milestone 1 is complete. Implementation commit: pending until the focused local
commit is created; record its hash here before finishing. Next implement
milestone 2 using Session 2 in `../docs/IMPLEMENTATION_PROMPTS.md`. Read current
status and this handoff; do not repeat the architecture research.

Start by reviewing `sadaf/settings.py`, `sadaf/runtime.py`, the legacy graph
schema, and migration code without instantiating graph/provider clients.
Implement SQLite memory behind an interface with read-only semantics, then test
only against temporary synthetic fixtures. Design dry-run, backed-up, idempotent
migration into a separate target. Do not read or migrate real legacy memories.
Commit only deliberate milestone 2 files/hunks; do not push.

## Context to retain

- Sadaf owns personal conversation, context, project policies, and reporting.
  M2 Harness supplies coding execution through a service interface.
- Global personal memory and project context have separate scopes and authority.
- Existing graph relationships are useful; safe transactional persistence comes
  before adding more retrieval complexity.
- Local Markdown project documents precede a concrete cloud adapter.
- Implement one milestone at a time, with offline verification and durable notes.
- The OpenRouter key may be configured; read it through settings, never echo it.
- Preserve prior edits listed in `EXISTING_WORK.md`; confirm current Git status
  because that inventory is only a starting snapshot.

## Open dependencies

Actual M2 protocol, cloud document service, live voice access, and measured model
selection remain unresolved. Milestone 1 is verified offline only. The legacy
graph has read-time pruning and unsafe migration behavior; milestone 2 must
preserve real memory and use synthetic fixtures.

## Suggested resume prompt

```text
Read AGENTS.md and .project-state/README.md, STATUS.md, and HANDOFF.md.
Continue milestone 1 using Session 1 in docs/IMPLEMENTATION_PROMPTS.md.
Preserve existing work, verify offline, and update the persistent state before finishing.
```
