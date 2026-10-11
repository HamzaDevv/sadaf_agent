# Existing work baseline

Snapshot before state scaffolding: 2026-10-11.
Branch: `feature/deepseek-v4-memory-architecture`.
HEAD: `6d81984`.

These files already had unfinished changes. This inventory records paths only;
it neither attributes their contents nor replaces inspection of current diffs.
Preserve unrelated work and stage explicit files/hunks for future commits.

## Tracked modifications

```text
.gitignore
brain/orchestrator.py
brain/pre_processor.py
brain/speaker_agent.py
config.py
llm_proxy/base.py
llm_proxy/deepseek_impl.py
llm_proxy/fallback_proxy.py
llm_proxy/gemini_impl.py
llm_proxy/groq_impl.py
main.py
memory/consolidator.py
memory/extractor.py
memory/graph_store.py
memory/memory_agent.py
requirements.txt
tools/news_tool.py
tools/registry.py
tools/reminder.py
tools/timer_tool.py
```

## Untracked paths

```text
.m2_cache/
audio/listener_continuous.py
audio/speaker_interruptible.py
brain/agent_core.py
brain/intent_resolver.py
docs/IMPLEMENTATION_PROMPTS.md
docs/REVIVAL_PLAN.md
generate_context.py
memory/compressor.py
reivew_to_improve.txt
repair/
test_deepseek.py
tools/tool_runtime.py
```

The two planning documents came from the preceding research session. No prior
application edits are claimed as completed implementation milestones.
