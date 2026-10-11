# Implementation roadmap

Detailed scope and prompts: [implementation prompts](../docs/IMPLEMENTATION_PROMPTS.md).
Design rationale: [revival plan](../docs/REVIVAL_PLAN.md).

| Milestone | Status | Completion evidence |
| --- | --- | --- |
| 0. Persistent development handoff | Complete | State files, repository instructions, verified links. |
| 1. Offline foundation | Complete | CPython 3.13.3 lockfile, validated role settings, safe offline doctor and fake text path, passing offline tests, focused local commit. Live providers remain unverified. |
| 2. Global memory | Pending | SQLite facts/episodes/edges with provenance and forget semantics, profile/persona separation, tested dry-run migration into separate data. |
| 3. Project context | Pending | Markdown sources, policy authority, isolation, revision snapshots, conflict and stale-context tests. |
| 4. Conversation and OpenRouter | Pending | Typed context, thread continuity, normalized provider/tools, offline tests; live smoke explicitly recorded when run. |
| 5. M2 task orchestration | Pending | Durable requests/receipts, fake lifecycle, restart/deduplication/concurrency tests; real adapter only against a supplied contract. |
| 6. Voice and integration | Pending | Replaceable transport, interruption handling, integrated offline scenarios; actual live voice evaluation separately recorded. |

Complete milestones sequentially. Partial progress belongs in `STATUS.md`;
do not advance a milestone just because its files exist. Provider credentials
and a real harness affect live integration, not completion of offline scaffolding.
