# Sadaf revival: personal partner, project context, and M2 delegation

Research date: 2026-10-10, Asia/Kolkata. Development handoff scaffolding added 2026-10-11; application architecture remains proposed. Current progress: [.project-state/STATUS.md](../.project-state/STATUS.md).

## Product goal

Sadaf is the persistent conversational partner. It understands the person, maintains separate project contexts, translates requests into constrained tasks, delegates execution to M2 Harness, and explains verified results. M2 remains responsible for coding execution. A voice interruption does not implicitly cancel a coding task.

“Consciousness” in this project means persistent personal context, shared history, current goals, and continuity of interaction. It is a product metaphor, not a claim that memory creates subjective consciousness.

## Work completed in this research session

- Reviewed the existing voice loop, V6/V7 agent paths, provider adapters, tools, graph storage, extractor, consolidation, legacy Markdown store, migration, and tests.
- Parsed 67 application/test Python files successfully. This establishes syntax validity only.
- Inspected memory inventory without running graph-store methods: 36 nodes, 10 edges, 10 session notes; no existing Markdown memory files found. No personal values are reproduced here.
- Stored the user-supplied OpenRouter key as `OPENROUTER_API_KEY` in `.env`; confirmed the file is Git-ignored. OpenRouter accepted a read-only `/api/v1/key` authentication check.
- Retrieved the public OpenRouter model catalog. No generation calls, audio capture, camera capture, memory migration, or application startup were performed.
- Existing tracked and untracked work was left in place. `.env` was the only existing file changed by this session; these two planning documents are new.
- No commit or provider switch was made. Session 1 below produces the first implementation commit.

## Model choices

These were initial research candidates, not a measured ranking of conversational quality. The 2026-10-11 cost update below supersedes their always-on use. Pin model IDs for evaluations rather than silently tracking latest aliases.

| Role | Starting candidate | Decision |
| --- | --- | --- |
| Conversational reasoning, project interpretation, M2 task preparation | OpenRouter `openai/gpt-6.1-sol` | Start at low reasoning effort for routine requests; use higher effort when task/policy complexity justifies it. |
| Extraction and background summaries | OpenRouter `openai/gpt-6-luna` | Require validated structured outputs and evidence. Compare against Sol before trusting durable writes. |
| Alternative main agent to evaluate | OpenRouter `anthropic/claude-sonnet-5.5` | Compare on the same tone, policy, clarification, and task-prompt scenarios. No assumption it is friendlier. |
| Difficult policy conflicts | OpenRouter `openai/gpt-6-astra` | Optional escalation after evaluations; excessive as an always-on default. |
| Preferred conversational voice frontend | Direct OpenAI `gpt-live-1`, client delegation | Voice stays responsive while our backend handles context, reasoning, M2, and result checks. Requires an OpenAI key and access validation. |
| Alternative unified voice model | Direct OpenAI `gpt-realtime-2.1` | Compare if a single voice/reasoning session is more practical. |
| Separate live speech recognition | Direct OpenAI `gpt-live-transcribe` | Use if we keep a chained architecture. Client-side speech endpoint detection is needed; this transcription model does not support server/semantic VAD. |
| Bounded recording transcription | Direct OpenAI `gpt-transcribe` | Useful for recorded fixtures and a completed-utterance path. |
| Offline development speech | Existing macOS `say` | Temporary fallback while validating the backend and waiting for an OpenAI key. |

## Cost-oriented provider update (2026-10-11)

The active legacy app now defaults to OpenRouter. Its reasoning, chat, agent,
and vision roles use `deepseek/deepseek-v4.1-flash:floor`, and the continuous
listener uses `qwen/qwen3-asr-0.6b`. The `:floor` suffix asks OpenRouter to pick
the lowest-priced available provider. This is a price-first routing choice;
availability, latency, and provider quality can vary. The newer standalone
backend retains fake defaults and selects the same DeepSeek route only when its
OpenRouter role is explicitly enabled.

The current catalog lists DeepSeek V4.1 Flash base rates around $0.13/M input
and $0.52/M output tokens, with discounted providers observed as low as
$0.0348/M and $0.1392/M respectively; provider prices change. Qwen3 ASR 0.6B
is listed at $0.000003/second. Optional Qwen Audio 3.0 TTS Flash is listed at
$15/M characters. TTS is opt-in via `SADAF_VOICE_PROVIDER=openrouter`; local
macOS `say` remains the default and has no provider charge. These rates are not
a quality comparison or a promised per-session cost.

Sources: [DeepSeek V4.1 Flash](https://openrouter.ai/deepseek/deepseek-v4.1-flash),
[OpenRouter floor route](https://openrouter.ai/blog/announcements/introducing-nitro-and-floor-price-shortcuts/),
[Qwen3 ASR 0.6B](https://openrouter.ai/qwen/qwen3-asr-0.6b),
[Qwen Audio 3.0 TTS Flash](https://openrouter.ai/qwen/qwen-audio-3.0-tts-flash),
[OpenRouter TTS guide](https://openrouter.ai/docs/guides/overview/multimodal/tts).
At the time this configuration update was made, no generation, transcription,
or synthesis request had been made.

### Synthetic live check (2026-10-11)

Within an explicit $0.15 test budget, DeepSeek V4.1 Flash `:floor` returned the
requested synthetic phrase (50 input, 45 output tokens). Qwen Audio 3.0 TTS
Flash returned MP3 audio for two short synthetic phrases. Qwen3 ASR 0.6B then
transcribed one generated sample as `The synthetic reference code is Kilo
Seven.` for 3.408 seconds of audio and reported $0.00001134864. Based on that
usage and the current catalog TTS rate, combined spend is estimated around
$0.00125. Two malformed ASR fixture requests returned 400 without usage fields,
so their billing status is unknown. No microphone or real conversation data was
used, and generated speech was not played. This is a connectivity and format
check, not a quality evaluation.

OpenRouter catalog base text rates observed: Sol $2 input / $10 output per million tokens; Luna $0.10 / $0.50; Sonnet 5.5 $2 / $10; Astra $10 / $50. These exclude reasoning-token effects, tools, cache writes, routing/account fees, and any long-context premiums. Do not treat a per-token rate as a per-conversation price. Official GPT-Live pricing was $0.05 per connected minute, with backend/tool costs separate: approximately $3 per connected hour before backend costs.

For direct OpenAI, current Sol/Astra function calling requires Responses API. OpenRouter offers a Responses endpoint but documents it as stateless: send conversation input explicitly, do not use `store:true` or `previous_response_id`. Confirm selected model/endpoint/tool behavior with contract tests; compatibility is not complete feature parity. The current repo's Chat Completions message-object contract should be normalized behind a provider interface.

The public OpenRouter catalog query did not return the named OpenAI Live/Realtime/transcription models. OpenRouter's file audio and streamed audio completion features do not establish support for the OpenAI Live session protocol. Keep speech and reasoning provider choices independent.

Some official TTS examples still show GPT-4o mini TTS, but the deprecation page announces retirement of its dated snapshots on 2027-01-06 and recommends Realtime 2.1 Mini. Avoid making legacy TTS the permanent foundation of a new integration.

## What the code already provides, and where it needs repair

| Area | Evidence in repository | Practical consequence |
| --- | --- | --- |
| Active architecture | `config.py` enables V7; `main.py` still constructs V6 components too | Establish one explicit entry point and documented compatibility boundaries. |
| Voice | `main.py` awaits listen, transcription, reasoning, and `say` sequentially | Continuous listener/interruptible speaker files alone do not give full duplex. |
| Retrieval | `memory/memory_agent.py` fuses vector, keyword, and graph ranks | Keep the hybrid retrieval idea; measure it against simpler lexical/vector baselines. |
| Network latency | Graph embedding and query operations are synchronous; retrieval invokes them on the async path | Offload blocking work and apply deadlines; lexical recall should still work offline. |
| Durable writes | `upsert_node` syncs Chroma before saving graph JSON | An embedding failure can prevent the fact from being durably saved. Write canonical data first and index through a retryable outbox. |
| Concurrent writes | Multiple consolidation tasks do whole-file read/modify/write with a shared `.tmp` path | Atomic rename does not prevent lost updates or conflicting temporary writes. |
| Retention | `get_all_nodes` prunes by time/salience, writes during reads, and retrieval does not call `access_node` | Protect the returning user's memories; keep reads side-effect-free and use explicit lifecycle jobs. |
| Corrections | Provisional confidence is `0.65 + 0.35 * salience`; promotion threshold is 0.70 | Many single statements promote immediately. Edge reinforcement is capped at 1.0 while promotion checks 1.05, so that branch cannot fire. |
| Evidence | Schema has `source_episode_id`, but consolidation does not populate it | Store exact supporting turn/episode IDs; inferred confidence must not be presented as proof. |
| Retry | Extractor catches provider exceptions and returns an empty patch | Consolidator cannot reliably distinguish “nothing to remember” from extraction failure. |
| Context | Compressor keeps a character tail and a few history lines | Preserve identity and policies explicitly; summarize threads and pending commitments instead of cutting blindly. |
| Tool execution | Several registry arguments differ from function signatures | Fix adapters/schemas, validate arguments, enforce deadlines, and return typed results. |
| Agent limit | Three-step loop can terminate with empty `final_spoken` | Return a useful incomplete/failure state rather than silence or false success. |
| Camera | `_camera_with_privacy` immediately invokes vision | Enforce the configured confirmation behavior in application code. |
| Migration | `scripts/migrate_memory.py` uses an outdated `upsert_node` signature | Do not run it on real data. Replace it with dry-run, idempotent migration. |
| Setup/tests | `google.genai` import does not match listed Google SDK; many tests instantiate the old live-service path | Provide clean offline setup, dependency injection, and tests for the active path. |

## Storage architecture

Use a hybrid design with clear ownership. Graphs encode relationships; Markdown encodes editable documents; transactional records encode events and state. None is universally the “best human memory.”

### Global personal context

- A human-maintained Markdown profile stores explicit communication preferences, enduring goals, and boundaries. Sadaf's own persona lives in a separate file so assistant traits cannot become user facts.
- A local SQLite database stores episodes, extracted facts, relationship edges, revisions, session events, extraction jobs, task receipts, and deletion markers. Scope every record by user and optional project.
- Profile overrides win over conflicting extracted preferences. Generated profile views are explicitly exports/projections of database facts, not another independently writable source of truth.
- A fact includes evidence ID, recorded time, effective/expiry time where applicable, confirmation state, sensitivity/export permission, and revision history. Stable identity facts are not automatically expired like moods.
- Provisional claims and confirmed corrections have different transitions. User-requested correction is explicit evidence; casual contradictory statements may require clarification. Model self-confidence is not truth probability.
- Retain episodic summaries for recall; generated reflections are marked as interpretations and link to evidence. Assistant output and quoted third-party text cannot silently become facts about the user.
- Forgetting removes the record from active retrieval, exports, lexical/vector indexes, and derived context; prevent queued extraction from resurrecting it. Backups and remote copies need an explicit retention policy.

SQLite is a small-footprint transactional starting point for this single-user app. It can store graph nodes/edges without deploying a graph server. Vector/lexical indexes are rebuildable projections. Start with SQLite FTS plus the graph; make vector indexing optional and benchmark the benefit before introducing another required cloud dependency. SQLite provides atomic transactions; this is the reason for the storage recommendation, not a claim that SQL resembles human cognition.

### Project context

Each registered project points to an explicit, authorized context root, initially local:

```text
project-context/
  INDEX.md
  PROJECT.md
  POLICIES.md
  ARCHITECTURE.md
  WORKING_STYLE.md
  DECISIONS.md
  OPEN_LOOPS.md
```

These are proposed filenames, not folders created in this session. Documents may later come from a cloud store. Each file has a project ID, revision/content hash, source, owner, trust classification, and status. Organization policies can be separately registered and attached to multiple projects.

Mandatory policies must be loaded deterministically, not left to similarity search. Retrieve task-specific architecture and decision sections selectively. Do not allow a conversation summary to rewrite an authoritative policy. Separate quoted/untrusted material from trusted rules.

The authority model is explicit: applicable binding organization/project rules constrain the task; project working style adjusts global preferences; conversational facts supply context. Conflicting mandatory rules require resolution, not an arbitrary winner chosen by a retrieval score. Users can amend policies only through the documented authorized update workflow.

Project selection is explicit session state. Every task pins its original project, document revisions, and relevant constraints. Switching the active project does not redirect existing tasks or import another project's private history. Include personal context in M2 requests only when relevant and permitted.

### Live/cloud documents

Implement a document-source interface for listing, reading by revision, and conditional updates. Local files are the first adapter. A later cloud adapter must use the chosen service's actual API, not assumed URLs or credentials.

Refresh the manifest on project activation and before task submission, then pin a coherent revision snapshot. If an important policy changes while work runs, flag that task for revalidation. Cache availability does not imply authority: show cache age and block governed dispatch when required policies cannot be verified. Do not silently replace them with empty context.

Use conditional writes/revision checks to prevent overwriting newer edits. For example, S3 supports `If-Match` and rejects mismatched ETags. That is a useful concurrency pattern, not a decision to deploy S3. Do not synchronize an open SQLite database by treating it as an ordinary cloud file; use a service or an application-level change log when multi-device access is added.

## Conversation and context assembly

Build a typed context packet from separate sections: persona, global profile, task-relevant memories, active project rules, relevant project knowledge, thread summary, recent exact turns, open commitments, and task state.

Policies and identity get reserved token budgets. The backend reasons from this packet; the voice model receives a concise speaking brief and verified results. Preserve exact source references in task requests even when prose is summarized. Do not add a mandatory extra LLM rewrite to every conversational turn.

Use per-thread summaries that preserve decisions, unresolved questions, corrections, and goals. Let users return to a thread after restart. Keep the raw transcript, cleaned transcript, and audible assistant output distinguishable so interrupted/unheard speech is not recorded as a completed exchange.

## M2 task receipts and multiple tasks

Treat M2 as one execution service with operations to submit, inspect, cancel, and retrieve results. The concrete wire API remains unknown; build against a protocol and a fake until the user provides its repository/interface.

A task request contains task ID, user/project/thread IDs, outcome, scope, repository/worktree reference, pinned policy sources/revisions, relevant decisions, dependencies, acceptance criteria, allowed actions, result expectations, and an idempotency key. A receipt contains the M2 run ID, state, timestamps, progress, artifacts, validation evidence, errors, and cancellation status.

Persist receipts and updates. Distinguish queued/running/awaiting-input/succeeded/failed/cancel-requested/cancelled; cancellation acceptance is not completion. Poll/event reconciliation survives reconnects and restarts. Deduplicate retries. Allow bounded concurrency for independent tasks, but queue tasks that mutate the same checkout unless M2 guarantees isolated worktrees. Track dependencies explicitly.

Sadaf reports policy checks and validation evidence without claiming comprehensive compliance from a model judgment. It cannot verify a result if M2 returns only a success string. Do not silently publish, deploy, or merge based on a spoken acknowledgment.

## Implementation order and two-day milestone

Use the six prompts in `docs/IMPLEMENTATION_PROMPTS.md`, sequentially in the same checkout. Each updates `.project-state/STATUS.md`, `HANDOFF.md`, and `SESSIONS.md` so a later session can reconstruct progress. `docs/IMPLEMENTATION_STATUS.md` points to that canonical record.

1. Offline foundation, settings, dependency injection, preservation safeguards, doctor, first implementation commit.
2. Transactional global memory, evidence, graph relationships, safe migration and rebuildable retrieval.
3. Project Markdown sources, policy authority, project isolation, revisioned context.
4. Conversation backend, OpenRouter adapter, normalized tools, continuity, typed context packets.
5. M2 protocol, prompt builder, durable receipts, fake workflows, real adapter if the interface is available.
6. Voice frontend, interruptions, live provider evaluation, integrated acceptance scenarios.

Day 1 target: foundation, safe scoped memory, project policy loading, and a working text conversation with a fake provider. Day 2 target: OpenRouter text flow, fake M2 task lifecycle, basic voice, and evaluation. A real M2 integration depends on its interface; full-duplex voice depends on access and audio behavior. Cloud synchronization, sophisticated graph traversal, and polished companionship are later milestones. Two days can deliver a meaningful vertical slice, not establish long-term reliability.

The first end-to-end scenario: recall a confirmed preference, activate project A, load its rules, submit two independent fake M2 tasks with policy revisions, keep chatting, switch to project B, receive A's results under A's scope, correct a personal memory, restart, and resume remaining task state without leakage or duplicate execution.

## Research sources

Recommendations above are engineering judgments informed by these sources; they are not claims that a paper proves this is the optimal architecture.

- [OpenAI model guidance](https://developers.openai.com/api/docs/guides/latest-model) and [model catalog](https://developers.openai.com/api/docs/models): role/cost tradeoffs and current endpoint requirements.
- [OpenRouter Sol](https://openrouter.ai/openai/gpt-6.1-sol), [Luna](https://openrouter.ai/openai/gpt-6-luna), [Sonnet](https://openrouter.ai/anthropic/claude-sonnet-5.5), and [public catalog](https://openrouter.ai/api/v1/models): verified slugs, prices, and advertised parameters.
- [OpenRouter quickstart](https://openrouter.ai/docs/quickstart), [tools](https://openrouter.ai/docs/guides/features/tool-calling), and [Responses overview](https://openrouter.ai/docs/api_reference/responses/overview): integration and stateless state handling.
- [GPT-Live](https://developers.openai.com/api/docs/guides/live), [client delegation](https://developers.openai.com/api/docs/guides/live-delegation), and [GPT-Live pricing](https://developers.openai.com/api/docs/models/gpt-live-1): voice/backend separation and application-owned context/task state.
- [Voice architectures](https://developers.openai.com/api/docs/guides/voice-agents), [live transcription](https://developers.openai.com/api/docs/guides/realtime-transcription), and [deprecations](https://developers.openai.com/api/docs/deprecations): audio choices and migration caveats.
- [Generative Agents](https://arxiv.org/abs/2304.03442): memory, retrieval, reflection, and planning as components of simulated agent behavior. It does not establish graphs as universally best.
- [MemGPT](https://arxiv.org/abs/2310.08560): separating context tiers and managing retrieval for conversations beyond a context window.
- [SQLite transactions](https://www.sqlite.org/transactional.html): atomic commit/rollback for concurrent durable state.
- [Chroma embedding functions](https://docs.trychroma.com/docs/embeddings/embedding-functions): local/remote embeddings and indexing responsibilities.
- [S3 conditional writes](https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes.html): a reference for cloud revision/concurrency checks.
