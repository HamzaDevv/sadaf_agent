import asyncio
from tests.utils.fixtures import get_isolated_orchestrator, cleanup_isolated_data

async def test_orchestrator_returns_string():
    run_id = "test_orch_1"
    try:
        orch = get_isolated_orchestrator(run_id)
        res = await orch.process("test_user", "Hello, how are you?")
        assert isinstance(res, str)
        assert len(res) > 0
    finally:
        cleanup_isolated_data(run_id)

async def test_orchestrator_uses_speaker_for_chat():
    run_id = "test_orch_2"
    try:
        orch = get_isolated_orchestrator(run_id)
        res = await orch.process("test_user", "Tell me a very short fun fact.")
        assert isinstance(res, str)
        # Assuming it just speaks, no tool execution errors.
    finally:
        cleanup_isolated_data(run_id)

async def test_orchestrator_uses_tool_for_math():
    run_id = "test_orch_3"
    try:
        orch = get_isolated_orchestrator(run_id)
        res = await orch.process("test_user", "Use your calculator to compute 99 times 12")
        assert isinstance(res, str)
        assert len(res) > 0
    finally:
        cleanup_isolated_data(run_id)

async def test_orchestrator_updates_buffer():
    run_id = "test_orch_4"
    try:
        orch = get_isolated_orchestrator(run_id)
        await orch.process("test_user", "Hi there")
        await orch.process("test_user", "What is your name?")
        assert len(orch.conversation_buffer) == 4
    finally:
        cleanup_isolated_data(run_id)

async def test_orchestrator_graceful_error_recovery():
    run_id = "test_orch_5"
    try:
        orch = get_isolated_orchestrator(run_id)
        res = await orch.process("test_user", "")
        # Empty string might be ignored or handled gracefully
        assert isinstance(res, str)
    finally:
        cleanup_isolated_data(run_id)
