import asyncio
import json
from types import SimpleNamespace

import pytest

from sadaf.conversation import (
    Completion, ContextBuilder, ContextBudgets, ConversationBackend, ConversationError,
    EvidenceMemory, OpenRouterProvider, ProviderError, SQLiteConversationStore, ToolCall,
    ToolRuntime, ToolSpec, Usage, memory_context,
)


def run(coro): return asyncio.run(coro)


def test_typed_context_reserves_policy_and_uses_section_budgets():
    builder = ContextBuilder(ContextBudgets(total_chars=80, reserved_policy_chars=20,
        persona_chars=10, profile_chars=10, summary_chars=10, recent_turn_chars=10,
        memory_chars=10, document_chars=10))
    packet = builder.build(user_id="u", thread_id="t", persona="p"*30, global_profile="g"*30,
        project_rules="r"*20, summary="s"*30,
        recent_turns=(), memories=(EvidenceMemory("f", "m"*100, "e", "turn", False),),
        project_documents=(("PROJECT.md", "d"*20),))
    assert packet.project_rules == "r"*20
    assert len(packet.persona) <= 10 and len(packet.global_profile) <= 10
    assert "provisional" in packet.render() if packet.memories else True
    with pytest.raises(ConversationError, match="Binding"):
        builder.build(user_id="u", thread_id="t", project_rules="r"*21)


def test_sqlite_thread_restart_summary_project_and_isolation(tmp_path):
    store = SQLiteConversationStore(tmp_path / "threads.sqlite")
    store.append("u1", "t", "A", __import__("sadaf.runtime", fromlist=["Turn"]).Turn("user", "hello"), __import__("sadaf.runtime", fromlist=["Turn"]).Turn("assistant", "hi"))
    store.append("u2", "t", "B", __import__("sadaf.runtime", fromlist=["Turn"]).Turn("user", "other"), __import__("sadaf.runtime", fromlist=["Turn"]).Turn("assistant", "reply"))
    store.save_summary("u1", "t", "Decision: remain in project A.")
    store.save_commitments("u1", "t", ["follow up"])
    state = SQLiteConversationStore(tmp_path / "threads.sqlite").load("u1", "t")
    assert state.project_id == "A" and len(state.turns) == 2
    assert state.summary.startswith("Decision") and state.commitments == ("follow up",)
    assert SQLiteConversationStore(tmp_path / "threads.sqlite").load("u2", "t").project_id == "B"


def test_thread_compaction_keeps_summary_and_recent_exact_exchange(tmp_path):
    from sadaf.runtime import Turn
    store = SQLiteConversationStore(tmp_path / "threads.sqlite")
    for i in range(4): store.append("u", "t", None, Turn("user", str(i)), Turn("assistant", "a"+str(i)))
    store.compact("u", "t", summary="Earlier decision: keep the task open.", keep_recent=4)
    state = store.load("u", "t")
    assert state.summary == "Earlier decision: keep the task open."
    assert [t.text for t in state.turns] == ["2", "a2", "3", "a3"]


def test_optional_summary_runs_at_threshold_and_persists(tmp_path):
    from sadaf.runtime import Turn
    store = SQLiteConversationStore(tmp_path / "threads.sqlite")
    provider = ScriptedProvider(Completion("a"), Completion("b"), Completion("c"))
    summarized = []
    async def summarizer(state):
        summarized.append(len(state.turns))
        return "Decision: keep the fixture task open; unresolved: none."
    backend = ConversationBackend(store=store, provider=provider, context_builder=ContextBuilder(),
        tool_runtime=ToolRuntime(), summarizer=summarizer, summarize_after_turns=4, summary_keep_recent=2)
    async def scenario():
        for text in ("one", "two", "three"):
            await backend.respond(user_id="u", thread_id="t", text=text)
    run(scenario())
    state = store.load("u", "t")
    assert summarized == [6]
    assert len(state.turns) == 2 and state.summary.startswith("Decision:")
    assert state.turns == (Turn("user", "three"), Turn("assistant", "c"))


class ScriptedProvider:
    def __init__(self, *responses): self.responses = list(responses); self.calls = []
    async def complete(self, messages, *, tools=()):
        self.calls.append((list(messages), list(tools)))
        response = self.responses.pop(0)
        if isinstance(response, Exception): raise response
        return response
    def stream(self, messages): yield "synthetic"


def test_backend_multi_turn_continuity_and_pinned_project(tmp_path):
    from sadaf.runtime import Turn
    store = SQLiteConversationStore(tmp_path / "threads.sqlite")
    provider = ScriptedProvider(Completion("first"), Completion("second"))
    backend = ConversationBackend(store=store, provider=provider, context_builder=ContextBuilder(), tool_runtime=ToolRuntime())
    async def scenario():
        await backend.respond(user_id="u", thread_id="t", project_id="A", text="one", project_rules="- MUST x=y")
        result = await backend.respond(user_id="u", thread_id="t", text="two", project_rules="- MUST x=y")
        return result
    result = run(scenario())
    assert result.text == "second"
    assert any(m.get("content") == "one" for m in provider.calls[1][0])
    with pytest.raises(ConversationError, match="pinned"):
        run(backend.respond(user_id="u", thread_id="t", project_id="B", text="switch"))


def test_backend_does_not_store_user_turn_when_provider_fails(tmp_path):
    store = SQLiteConversationStore(tmp_path / "threads.sqlite")
    backend = ConversationBackend(store=store, provider=ScriptedProvider(ProviderError("offline")), context_builder=ContextBuilder(), tool_runtime=ToolRuntime())
    with pytest.raises(ProviderError): run(backend.respond(user_id="u", thread_id="t", text="fixture"))
    assert store.load("u", "t").turns == ()


def test_tools_validate_arguments_offload_and_return_structured_failures():
    seen = []
    spec = ToolSpec("sum", "sum numbers", {"type":"object","properties":{"n":{"type":"integer"}},"required":["n"],"additionalProperties":False}, lambda n: seen.append(n) or n+1)
    runtime = ToolRuntime([spec])
    good = run(runtime.execute(ToolCall("1", "sum", {"n":2})))
    bad = run(runtime.execute(ToolCall("2", "sum", {"n":"2"})))
    unknown = run(runtime.execute(ToolCall("3", "missing", {})))
    assert good == {"ok":True,"result":3} and seen == [2]
    assert bad["error"] == "invalid_tool_arguments" and unknown["error"] == "unknown_tool"


def test_camera_requires_explicit_runtime_confirmation():
    called = []
    spec = ToolSpec("camera", "camera", {"type":"object","properties":{},"additionalProperties":False}, lambda: called.append(True), privacy="camera")
    assert run(ToolRuntime([spec]).execute(ToolCall("c", "camera", {})))["error"] == "camera_use_not_confirmed"
    assert not called
    assert run(ToolRuntime([spec], camera_confirmation=lambda: True).execute(ToolCall("c", "camera", {})))["ok"]


def test_legacy_tool_adapter_maps_registry_arguments_to_real_signatures(monkeypatch):
    from sadaf.conversation import legacy_tool_specs
    captured = []
    monkeypatch.setattr("sadaf.conversation.importlib.import_module",
                        lambda module: SimpleNamespace(get_countdown=lambda query: captured.append(query) or "fixture"))
    specs = {spec.name:spec for spec in legacy_tool_specs()}
    result = run(ToolRuntime([specs["get_countdown"]]).execute(ToolCall("c", "get_countdown", {"target":"Friday"})))
    assert captured == ["Friday"] and result == {"ok":True,"result":"fixture"}
    assert specs["get_countdown"].parameters["required"] == ["target"]


def test_legacy_camera_adapter_blocks_before_import_without_confirmation(monkeypatch):
    from sadaf.conversation import legacy_tool_specs
    def forbidden(*args, **kwargs): raise AssertionError("camera import or execution must not happen")
    monkeypatch.setattr("sadaf.conversation.importlib.import_module", forbidden)
    camera = next(spec for spec in legacy_tool_specs() if spec.name == "camera_tool")
    result = run(ToolRuntime([camera]).execute(ToolCall("c", "camera_tool", {"query":"fixture"})))
    assert result == {"ok":False,"error":"camera_use_not_confirmed"}


def test_tool_iteration_exhaustion_is_truthfully_incomplete(tmp_path):
    from sadaf.runtime import Turn
    store = SQLiteConversationStore(tmp_path / "threads.sqlite")
    tool = ToolSpec("ping", "ping", {"type":"object","properties":{},"additionalProperties":False}, lambda: "pong")
    repeated = Completion(tool_calls=(ToolCall("c", "ping", {}),), finish_reason="tool_calls")
    provider = ScriptedProvider(repeated, repeated)
    backend = ConversationBackend(store=store, provider=provider, context_builder=ContextBuilder(), tool_runtime=ToolRuntime([tool]), max_tool_rounds=1)
    result = run(backend.respond(user_id="u",thread_id="t",text="do it"))
    assert result.incomplete and "tool-call limit" in result.text
    assert store.load("u", "t").turns[-1] == Turn("assistant", result.text)


def test_openrouter_normalizes_calls_usage_and_minimal_payload():
    requests = []
    def transport(url, headers, data, timeout):
        requests.append((url, headers, json.loads(data), timeout))
        return 200, json.dumps({"choices":[{"finish_reason":"tool_calls","message":{"content":None,"tool_calls":[{"id":"c1","function":{"name":"f","arguments":"{\"x\":1}"}}]}}],"usage":{"prompt_tokens":5,"completion_tokens":2}}).encode()
    provider = OpenRouterProvider("synthetic-key", transport=transport, fallback_model=None)
    result = run(provider.complete([{"role":"user","content":"synthetic"}], tools=[{"type":"function"}]))
    assert requests[0][0].endswith("/chat/completions")
    payload = requests[0][2]
    assert payload["model"] == "deepseek/deepseek-v4.1-flash:floor" and payload["stream"] is False
    assert "temperature" not in payload and "store" not in payload and "previous_response_id" not in payload
    assert result.tool_calls == (ToolCall("c1","f",{"x":1}),) and result.usage == Usage(5,2)


def test_openrouter_capability_failure_and_retry_bounds():
    provider = OpenRouterProvider("synthetic-key", capabilities=(), transport=lambda *args: pytest.fail("must not call transport"))
    with pytest.raises(ProviderError, match="not declared"):
        run(provider.complete([], tools=[{"type":"function"}]))
    seen = []
    def flaky(*args):
        seen.append(1)
        return (429, b"rate limited") if len(seen) == 1 else (200, b'{"choices":[{"message":{"content":"ok"}}]}')
    provider = OpenRouterProvider("synthetic-key", retries=1, transport=flaky)
    assert run(provider.complete([])).text == "ok" and len(seen) == 2


def test_openrouter_malformed_tool_arguments_are_not_executable():
    provider = OpenRouterProvider("synthetic-key", transport=lambda *args: (200, b'{"choices":[{"message":{"tool_calls":[{"id":"c","function":{"name":"x","arguments":"oops"}}]}}]}'))
    completion = run(provider.complete([]))
    assert completion.tool_calls[0].arguments is None


def test_openrouter_stream_normalizes_sse_deltas(monkeypatch):
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def __iter__(self):
            yield b'data: {"choices":[{"delta":{"content":"syn"}}]}\n'
            yield b'data: {"choices":[{"delta":{"content":"thetic"}}]}\n'
            yield b'data: {"choices":[],"usage":{"prompt_tokens":3,"completion_tokens":2}}\n'
            yield b'data: [DONE]\n'
    monkeypatch.setattr("sadaf.conversation.urlopen", lambda *args, **kwargs: Response())
    provider = OpenRouterProvider("synthetic-key")
    assert "".join(provider.stream([{"role":"user","content":"fixture"}])) == "synthetic"
    events = list(provider.stream_events([{"role":"user","content":"fixture"}]))
    assert events[-1].usage == Usage(3, 2)


def test_conversation_routes_malformed_tool_call_as_safe_observation(tmp_path):
    from sadaf.runtime import Turn
    store = SQLiteConversationStore(tmp_path / "threads.sqlite")
    provider = ScriptedProvider(Completion(tool_calls=(ToolCall("bad", "noop", None),)), Completion("recovered"))
    backend = ConversationBackend(store=store, provider=provider, context_builder=ContextBuilder(), tool_runtime=ToolRuntime())
    result = run(backend.respond(user_id="u",thread_id="t",text="fixture"))
    assert result.text == "recovered"
    assert result.tool_observations == ({"ok":False,"error":"malformed_tool_arguments"},)
    assert store.load("u", "t").turns == (Turn("user","fixture"), Turn("assistant","recovered"))


def test_memory_adapter_preserves_evidence_and_export_limits():
    class Fact:
        id="f1"; section="preferences"; key="tone"; value="concise"; source_episode_id="e1"; source_turn_id="t1"; status="confirmed"; allow_export=True; sensitivity="personal"
    class Repo:
        def read_profile(self, user): return "## Preferences\n- concise"
        def read_persona(self): return "Persona"
        def recall(self, *args, **kwargs): return type("Recall", (), {"facts":(Fact(),)})()
    persona, profile, facts = memory_context(Repo(), user_id="u", query="tone")
    assert persona == "Persona" and "concise" in profile
    assert facts[0].source_episode_id == "e1" and facts[0].confirmed


def test_memory_adapter_excludes_sensitive_and_nonexportable():
    class Fact:
        id="f"; section="x"; key="y"; value="z"; source_episode_id=None; source_turn_id=None; status="provisional"; allow_export=False; sensitivity="sensitive"
    class Repo:
        read_profile=lambda *a: ""; read_persona=lambda *a: ""
        recall=lambda *a, **k: type("Recall", (), {"facts":(Fact(),)})()
    assert memory_context(Repo(), user_id="u", query="x")[2] == ()
