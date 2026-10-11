# Next-session handoff

Updated: 2026-10-11 (Asia/Kolkata).

## Resume here

Milestones 1–3 are complete offline. Milestone 1 implementation commit:
`b1eeb43bfa7b8cbbac99dba8bcb6164377d60085`. Milestone 2 implementation commit:
`fd5fa2672d62c2cbf79a48aa77fc5228408c98ff` (verified in this session).
Milestone 3 implementation commit: `578282502bc7ff81bbacb24107cbe2fd80a6ccc3`.
Next implement milestone 4 using Session 4 in `../docs/IMPLEMENTATION_PROMPTS.md`.
Do not repeat architecture research or implement an invented M2/cloud API.

Build a typed context packet and conversation backend with thread continuity,
OpenRouter/provider normalization, and validated tool adapters. Start with fakes,
then run a minimal live text smoke only when its contract/access is available.
Distinguish live results from simulated checks. Preserve unrelated checkout work,
use explicit staging, and do not push.

## Milestone 3 interfaces and verification

- `../sadaf/projects.py`: registry, document-source protocol, local revision/CAS
  adapter, immutable snapshots, policy authority, scoped context selection.
- `../docs/PROJECT_CONTEXT.md`: format, usage, authorization boundaries, limits.
- `../tests_offline/test_projects.py`: temporary projects and opaque-revision fake.
- `ProjectContext.prepare_dispatch` refreshes the explicit original project and
  blocks missing/stale/unavailable/conflicting/oversized policies. Integrate this
  into future task preparation; no actual dispatch is implemented yet.
- Project switching does not redirect pinned snapshots. `revalidate` flags policy
  changes for review, knowledge changes, and unavailable/blocked required context.
- 84 tests passed; offline locked sync, compileall, doctor, fake text, and wheel
  build/template initialization passed. No real memories or live service touched.

## Context and limits to retain

- Sadaf owns personal conversation, project context/policies, and reporting;
  M2 supplies coding execution through its eventual actual service contract.
- Organization/project binding documents load in full. Keyed MUST conflicts block;
  prose conflicts require review. Project style overlays supplied global preferences;
  arbitrary Markdown stays untrusted. Personal memory is not exported here.
- Registry/source grants and actor authentication are trusted-host responsibilities.
  Local roots cannot overlap; shared organization policies have separate roots.
- Local updates serialize cooperating Unix/macOS writers; external editors can race
  final replacement. Multi-source revision snapshots are optimistic. Do not claim
  universal file CAS or distributed atomicity. Revision archive retention/audit
  history remain future work; initial templates are not owner approval.
- The layer is standalone; running-task pause/revalidation actions, cloud sync,
  OpenRouter conversation integration, and M2 dispatch remain future milestones.
- Real M2 needs its repository/API contract; cloud source selection and measured
  model choice remain unresolved. Direct OpenAI voice requires separate access.
- Legacy graph reads can prune data. Do not open or migrate real legacy memories.
- Preserve existing edits/untracked files in `EXISTING_WORK.md`; inspect current
  status because the inventory is only a baseline. No real-memory data or secrets
  belong in this handoff.

## Suggested resume prompt

```text
Read AGENTS.md and .project-state/README.md, STATUS.md, and HANDOFF.md.
Continue milestone 4 using Session 4 in docs/IMPLEMENTATION_PROMPTS.md.
Preserve existing work, verify offline, and update persistent state before finishing.
```
