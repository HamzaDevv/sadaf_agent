# Sequential implementation prompts

Run these in order in this repository. Each is independently pasteable into a new session, but depends on the previous milestone's files. Do not run multiple sessions against the same checkout concurrently. Read `REVIVAL_PLAN.md` for the agreed direction and `../.project-state/README.md`, `STATUS.md`, and `HANDOFF.md` for continuity. `IMPLEMENTATION_STATUS.md` links to the canonical state. Development-state scaffolding is complete; application milestones remain pending. Update persistent status, handoff, and session log after each milestone.

## Session 1: offline foundation and first commit

```text
Implement milestone 1 for Sadaf in this repository. Read docs/REVIVAL_PLAN.md, inspect any AGENTS.md instructions and git status, and preserve all pre-existing tracked/untracked work. Sadaf is the personal conversational partner; project context is separate; M2 Harness handles coding execution. Do not rewrite the app wholesale.

Create a reproducible Python setup with explicit supported Python version, appropriate dependency constraints, developer test dependencies, and separate optional audio/vector dependencies. Fix the google.genai dependency mismatch. Add validated role-based settings for reasoning, extraction, voice, embeddings, data paths, and M2 endpoint; support OPENROUTER_API_KEY already in .env without displaying it. Create a placeholder-only .env.example.

Remove import-time provider/client initialization from the new entry point and default offline tests; use injected providers/stores. Provide an offline doctor command and minimal text-mode path using fakes. Prevent development startup from modifying/pruning legacy memories, and document the existing graph migration hazard. Add meaningful setup/configuration tests that need no keys, hardware, or network.

Update .project-state/STATUS.md and HANDOFF.md with completed work, verification, unresolved decisions, and the exact next milestone; append to SESSIONS.md. Keep docs/IMPLEMENTATION_STATUS.md as a pointer to that canonical state and consult .project-state/EXISTING_WORK.md for prior edits. Verify the offline doctor and tests. Make the first local implementation commit using explicit file/hunk selection for only this milestone's changes; preserve unrelated edits and never stage secrets, personal memories, runtime caches, or whole-directory contents blindly. Do not push. Report the commit hash, tests, and remaining limitations.
```

## Session 2: global memory with provenance and safe migration

```text
Implement milestone 2 for Sadaf. Read docs/REVIVAL_PLAN.md, docs/IMPLEMENTATION_STATUS.md, applicable repository instructions, and git status. Confirm milestone 1 exists; preserve unrelated work. Keep all normal tests offline.

Implement SQLite-backed episodes, facts, relationship edges, revisions, extraction jobs/outbox, and user/project scopes behind a memory-store interface. Preserve the useful graph model without requiring a graph server. Store source turn/episode IDs, confirmation state, timestamps, sensitivity/export permissions, and time validity. Protect enduring identity/preferences from automatic age-based deletion. Reads must not mutate or prune state. Define explicit correction, provisional conflict, expiry, and forget transitions; forget must remove derived/indexed retrieval and prevent queued jobs from restoring deleted facts.

Add a separately editable global profile Markdown file and assistant-persona file. Document their authority: explicit profile preferences override extracted preferences; generated memory exports are projections, not independently writable copies. Use lexical retrieval first and optional rebuildable vector indexing. Canonical writes must succeed independently of embedding services. Validate extraction patches and distinguish failed extraction from no facts.

Replace the broken legacy migration with dry-run, backup-aware, idempotent import into a separate target. Test using copied synthetic graph/archive/episode fixtures; do not migrate or prune the real memories directory without an explicit later migration request. Test concurrent writes, evidence links, corrections, deletion, offline recall, restart, and repeat import. Update implementation status, commit only this milestone's changes locally without pushing, and report limitations.
```

## Session 3: project Markdown and authoritative policies

```text
Implement milestone 3 for Sadaf. Read docs/REVIVAL_PLAN.md, docs/IMPLEMENTATION_STATUS.md, applicable repository instructions, and git status. Confirm earlier milestones exist and preserve unrelated work.

Create a project registry with explicit project identity, authorized context root, repository reference, and active-project session state. Provide local Markdown templates for INDEX, PROJECT, POLICIES, ARCHITECTURE, WORKING_STYLE, DECISIONS, and OPEN_LOOPS. Build a document-source interface with read/list/revision operations and conditional updates. Implement the local adapter now and test cloud-style revision conflicts through a fake; do not invent cloud endpoints or credentials.

Separate organization policy, binding project rules, working style, user preferences, and untrusted source content. Load required policies deterministically and retrieve task-specific document sections selectively. Reserve space for binding rules; surface mandatory conflicts or oversized policy sets instead of silently truncating them. Conversation cannot silently rewrite policies. Scope knowledge and history to the selected project, validate paths including symlink escapes, and prevent cross-project retrieval.

Refresh document revisions before task dispatch and pin coherent snapshots. Define behavior for unavailable/stale required policies and for policy changes during an existing task. Test project switching, global preference overlays, rule conflicts, external edits, stale cache, and project isolation. Update implementation status and make a local commit containing only this milestone's changes; do not push.
```

## Session 4: conversation backend and OpenRouter

```text
Implement milestone 4 for Sadaf. Read docs/REVIVAL_PLAN.md, docs/IMPLEMENTATION_STATUS.md, applicable repository instructions, and git status. Confirm the scoped memory and project-document interfaces exist. Preserve unrelated work.

Build one active text conversation backend with injected storage, project context, provider, and tool runtime. Assemble typed context packets with persona, global profile, relevant evidence-backed memories, binding project rules, selected project documents, thread summary, recent exact turns, commitments, and task state. Replace character-tail truncation with explicit budgets and durable thread summaries. Keep summaries distinguishable from confirmed facts and authoritative policies.

Implement an OpenRouter adapter using OPENROUTER_API_KEY from .env. Verify current official endpoint/model capabilities before choosing Chat Completions versus Responses. Start with openai/gpt-6.1-sol for main reasoning and openai/gpt-6-luna for extraction, configurable by role. Normalize response, streaming, tool calls, usage, and error types. For OpenRouter Responses, maintain conversation state locally and do not send store:true or previous_response_id. Add deadlines, bounded retries, provider capability checks, and declared fallbacks. Do not send unsupported generic parameters to every model.

Repair existing tool schema/signature mismatches, validate arguments, offload blocking calls, and return structured tool observations. Handle iteration exhaustion with a useful incomplete state. Enforce camera privacy behavior in code. Test multi-turn correction/clarification, restart continuity, streaming, malformed calls, tool failures, policies retained under budget, and thread/project isolation with fakes. Add an opt-in bounded live smoke command using synthetic input only. Update implementation status and commit only this milestone locally; do not push.
```

## Session 5: M2 task requests and durable receipts

```text
Implement milestone 5 for Sadaf. Read docs/REVIVAL_PLAN.md, docs/IMPLEMENTATION_STATUS.md, applicable repository instructions, and git status. Preserve unrelated work. M2 is the coding execution service; Sadaf owns context, conversation, task preparation, and evidence-based reporting.

Define an M2Client protocol and fake with submit/status/cancel/result operations. Create typed task requests carrying user/project/thread IDs, outcome, scope, repository/worktree reference, dependencies, pinned policy sources/revisions, relevant decisions, acceptance criteria, allowed actions, result requirements, and idempotency keys. Store task receipts and lifecycle events transactionally, including M2 run ID, progress, artifacts, validation evidence, errors, and cancellation state.

Support multiple independent tasks per project with bounded concurrency. Serialize tasks that mutate the same checkout unless the real harness supplies isolation. Preserve original project/revisions when the user changes active project. Keep conversation responsive while tasks run. Distinguish speech interruption, cancel request, accepted cancellation, and confirmed cancellation. Reconcile after restart without duplicate submissions and flag policy changes for revalidation. Send only necessary, permitted personal context to M2.

Inspect the real M2 interface if provided; otherwise ask for its repo/API contract while completing the fake end-to-end flow. Do not invent endpoints or call unrelated tools as M2. Test failure, partial results, clarification, dependencies, deduplication, same-checkout conflicts, stale policy, restart, and result attribution. Report success only from returned evidence. Update implementation status and commit only this milestone locally; do not push.
```

## Session 6: conversational voice and integrated evaluation

```text
Implement milestone 6 for Sadaf. Read docs/REVIVAL_PLAN.md, docs/IMPLEMENTATION_STATUS.md, applicable repository instructions, and git status. Preserve unrelated work and verify which backend/M2 milestones actually work before building on them.

Provide a replaceable voice transport around the existing conversation backend. Verify current official GPT-Live client-delegation docs and available account access. Prefer direct OpenAI gpt-live-1 for natural voice while our backend manages scoped context, OpenRouter reasoning, and M2. If OPENAI_API_KEY is unavailable, finish the fake voice transport, event tests, and macOS speech fallback, and clearly identify live voice as unverified. Do not assume the OpenRouter key authenticates OpenAI Live. A chained fallback may use gpt-live-transcribe with client-side endpoint detection; check current deprecations before adding a permanent TTS provider.

Implement speech/listening events, transcript reconciliation, interruption, playback stop, context synchronization, reconnection, and graceful shutdown. Track actual audible output so unplayed speech is not treated as heard. Pausing voice does not cancel background coding tasks unless explicitly requested. Preserve policy enforcement in the backend. For Live client delegation, prepare task text from application transcripts/state rather than assuming the delegation event contains the full request.

Run offline integrated scenarios covering memory correction, project switching, policy retention, concurrent fake M2 tasks, interruption, restart, and truthful result reporting. Add opt-in live microphone evaluation and measurements for useful-answer latency, interruption recovery, recognition of names/numbers/language switches, and session cost. Compare model candidates on identical representative scenarios before claiming a winner. Update implementation status, record live versus simulated validation distinctly, and commit only this milestone locally without pushing.
```
