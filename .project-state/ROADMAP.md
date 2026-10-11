# Implementation roadmap

Detailed scope and prompts: [implementation prompts](../docs/IMPLEMENTATION_PROMPTS.md).
Design rationale: [revival plan](../docs/REVIVAL_PLAN.md).

| Milestone | Status | Completion evidence |
| --- | --- | --- |
| 0. Persistent development handoff | Complete | State files, repository instructions, verified links. |
| 1. Offline foundation | Complete | CPython 3.13.3 lockfile, validated role settings, safe offline doctor and fake text path, passing offline tests, focused local commit. Live providers remain unverified. |
| 2. Global memory | Complete | Scoped SQLite episodes/facts/edges/revisions/outbox, read-only lexical recall, correction/expiry/forget lifecycle, editable profile/persona, offline concurrency and migration tests against synthetic fixtures. |
| 3. Project context | Complete offline | Authorized scoped registry, seven Markdown templates, local revision archive/conditional updates, full policy authority and blockers, selective knowledge, immutable snapshots/revalidation flags; `578282502bc7ff81bbacb24107cbe2fd80a6ccc3`; 84 offline tests. Prose conflict review, external-editor CAS races, and runtime orchestration remain limitations. |
| 4. Conversation and OpenRouter | Complete offline | Typed context budgets, durable scoped thread continuity/summaries, memory/project integration, normalized OpenRouter Chat Completions and tools, opt-in synthetic live smoke; `d6490961a3fb1c6921f9ac06316011f23bb74a2b`; 103 offline tests. Live provider access remains unverified. |
| 5. M2 task orchestration | Complete offline | Typed requests/client protocol, transactional receipts/events, fake submit/status/cancel/result lifecycle, restart reconciliation, idempotency, dependencies, checkout serialization, cancellation distinctions, original project/policy attribution, and revalidation flags; 113 offline tests. No real M2 contract or adapter. |
| 6. Voice and integration | Complete offline; live evaluation pending | Replaceable controller/fake transport, macOS speech fallback, transcript/delivery ledgers, interruption, context synchronization, reconnect/shutdown, opt-in evaluation hook, and integrated temporary-fixture scenarios; 127 offline tests. No live voice/microphone or real M2 adapter. |

Complete milestones sequentially. Partial progress belongs in `STATUS.md`;
do not advance a milestone just because its files exist. Provider credentials
and a real harness affect live integration, not completion of offline scaffolding.

2026-10-11 provider cost update: the legacy app now defaults to OpenRouter
DeepSeek V4.1 Flash `:floor` and Qwen3 ASR 0.6B. Optional paid Qwen Audio 3.0
TTS Flash is available; local macOS speech remains default. Tiny synthetic live
requests checked chat/TTS/ASR reachability within the user's $0.15 limit. No
provider quality evaluation or microphone/playback check was performed.
