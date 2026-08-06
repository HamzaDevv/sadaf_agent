import os
from config import GROQ_API_KEYS, BOSS_MODEL, SUBAGENT_MODEL
from llm_proxy import llm_proxy
from tools.registry import TOOL_REGISTRY
from tests.utils.fixtures import get_isolated_memory_store, cleanup_isolated_data

def test_groq_api_keys_configured():
    assert len(GROQ_API_KEYS) > 0, "No Groq API keys found in config"

def test_llm_proxy_singleton():
    assert llm_proxy is not None, "llm_proxy singleton failed to initialize"
    assert len(llm_proxy.keys) > 0, "llm_proxy has no keys"

def test_memory_store_init():
    run_id = "smoke_test"
    try:
        store = get_isolated_memory_store(run_id)
        assert store is not None
        assert os.path.exists(store.root)
    finally:
        cleanup_isolated_data(run_id)

def test_tool_registry_count():
    assert len(TOOL_REGISTRY) >= 15, f"Expected at least 15 tools, found {len(TOOL_REGISTRY)}"

def test_tool_registry_fields():
    for tool in TOOL_REGISTRY:
        assert tool.name, "Tool is missing a name"
        assert tool.description, f"Tool {tool.name} is missing a description"
        assert callable(tool.tool_fn), f"Tool {tool.name} tool_fn is not callable"

def test_config_models_defined():
    assert BOSS_MODEL and isinstance(BOSS_MODEL, str)
    assert SUBAGENT_MODEL and isinstance(SUBAGENT_MODEL, str)

def test_pre_processor_imports():
    from brain.pre_processor import analyze_input
    assert callable(analyze_input)
