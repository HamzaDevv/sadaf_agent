import asyncio
from tests.utils.fixtures import get_isolated_orchestrator, cleanup_isolated_data
from tests.utils.ai_judge import score_memory_recall
from memory.schemas import MemoryNode

async def test_workflow_ltm_retrieval():
    run_id = "wf_ltm"
    user_id = "test_alex"
    try:
        orch = get_isolated_orchestrator(run_id)
        store = orch.memory.store
        store.ensure_user_dir(user_id)
        
        # Pre-seed memory
        store.upsert_node(user_id, MemoryNode(node_id="identity:name", section="identity", key="name", value="Alex Raza"))
        store.upsert_node(user_id, MemoryNode(node_id="identity:occupation", section="identity", key="occupation", value="AI Engineer"))
        store.upsert_node(user_id, MemoryNode(node_id="preference:drink", section="preference", key="drink", value="Flat White coffee"))
        store.upsert_node(user_id, MemoryNode(node_id="preference:hobby", section="preference", key="hobby", value="Playing chess"))
        store.upsert_node(user_id, MemoryNode(node_id="pet:dog_name", section="pet", key="dog_name", value="Max"))
        store.upsert_node(user_id, MemoryNode(node_id="goal:current", section="goal", key="current", value="Learning Rust programming"))
        
        # We need to test queries and see if the orchestrator recalls these facts
        queries = [
            ("What do I like to drink?", ["Flat White coffee"]),
            ("What's my dog's name?", ["Max"]),
            ("What am I learning these days?", ["Rust"]),
            ("What is my job?", ["AI Engineer"])
        ]
        
        correct = 0
        
        for q, expected_facts in queries:
            # Clear boss buffer so it doesn't just use short-term memory
            orch.conversation_buffer.clear()
            
            res = await orch.process(user_id, q)
            
            # Evaluate
            judge_res = await score_memory_recall(q, res, expected_facts)
            if judge_res.get("success", False) or judge_res.get("accuracy", 0.0) >= 0.7:
                correct += 1
                
        accuracy = correct / len(queries)
        assert accuracy >= 0.75, f"Recall accuracy too low: {accuracy * 100}%"
        
    finally:
        cleanup_isolated_data(run_id)
