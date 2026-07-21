import asyncio
from brain.pre_processor import analyze_input

async def test_pre_processor_exit_intent():
    res = await analyze_input("goodbye, see you later")
    assert res["intent"] == "exit", f"Expected exit, got {res['intent']}"
    assert res["emotion"] == "neutral"

async def test_pre_processor_pause_intent():
    res = await analyze_input("hold on, wait a second")
    assert res["intent"] == "pause", f"Expected pause, got {res['intent']}"

async def test_pre_processor_filler_not_pause():
    res = await analyze_input("um, uh... I was thinking")
    assert res["intent"] == "converse", f"Expected converse, got {res['intent']}"

async def test_pre_processor_question():
    res = await analyze_input("what is the weather today?")
    assert res["intent"] == "converse", f"Expected converse, got {res['intent']}"

async def test_pre_processor_emotional_input():
    res = await analyze_input("this is so frustrating!")
    assert res["intent"] == "converse"
    assert res["emotion"] == "frustrated", f"Expected frustrated, got {res['emotion']}"

async def test_pre_processor_capabilities():
    res = await analyze_input("what can you do?")
    assert res["intent"] == "capabilities_query", f"Expected capabilities_query, got {res['intent']}"
