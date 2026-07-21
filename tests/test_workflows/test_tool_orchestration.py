import asyncio
from tests.utils.fixtures import get_isolated_subsystems, cleanup_isolated_data

async def run_tool_routing_test(query: str, expected_tool: str) -> bool:
    run_id = "wf_tool_orchestration"
    try:
        _, _, _, tool_subagent, _ = get_isolated_subsystems(run_id)
        
        # We test the Tool Subagent's routing intelligence directly.
        # If we pass a conversation query, we expect it to return failure (tool_name: null).
        res = await tool_subagent.execute(task_description=query, user_query=query)
        
        tool_used = res.get("tool_used")
        
        if expected_tool is None:
            # We expect it to NOT use a tool
            return tool_used is None
            
        return tool_used == expected_tool
    finally:
        cleanup_isolated_data(run_id)

async def test_workflow_tool_orchestration():
    queries = [
        # Category A: Single clear tool call
        ("What is 45 times 89?", ["calculate"]),
        ("What time is it right now?", ["get_datetime"]),
        ("Set a timer for 5 minutes", ["set_timer"]),
        ("What's the weather like?", ["get_weather"]),
        
        # Category B: Multi-concept query
        ("Search for the latest news on AI and summarize it", ["web_search"]),
        ("Check the weather in Tokyo", ["get_weather", "web_search"]),
        
        # Category C: Pure Conversation (Should not pick a tool, Boss would route to speaker anyway, but if forced, tool subagent should fail to find a tool)
        ("How are you doing today?", [None]),
        ("Tell me something interesting", [None, "web_search"]),
        
        # Category D: Unaddressable / Out-of-Scope
        ("Order a pizza to my house", [None, "web_search"]),
        ("Hack into the mainframe", [None, "web_search"])
    ]
    
    correct = 0
    for q, expected_list in queries:
        # Some flexibility for search fallbacks
        passed = False
        for exp in expected_list:
            if await run_tool_routing_test(q, exp):
                passed = True
                break
                
        if passed:
            correct += 1
        else:
            print(f"Failed routing for '{q}'. Expected one of: {expected_list}")
            
    accuracy = correct / len(queries)
    assert accuracy >= 0.80, f"Tool routing accuracy too low: {accuracy * 100}%"
