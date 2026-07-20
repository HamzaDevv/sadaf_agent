import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from memory.graph_store import MemoryGraphStore
from memory.consolidator import MemoryConsolidator
from config import DEFAULT_USER_ID

async def run_test():
    print("--- Testing Contradiction Detection & Resolution ---")
    store = MemoryGraphStore()
    consolidator = MemoryConsolidator(store)

    # 1. Setup baseline fact
    store.upsert_node(DEFAULT_USER_ID, "career", "company", "Accenture")
    store.upsert_node(DEFAULT_USER_ID, "emotions", "state", "Happy")
    
    print("\nInitial nodes:")
    print(store.get_nodes_summary(DEFAULT_USER_ID))

    # 2. Test High Importance Contradiction (Job Company change)
    print("\n[Turn 1] User says: 'I just got hired at Google today as an engineer.'")
    await consolidator.consolidate(
        DEFAULT_USER_ID,
        "I just got hired at Google today as an engineer.",
        "That's incredible news! Congratulations on joining Google!"
    )

    pending = store.get_pending_contradictions(DEFAULT_USER_ID)
    print(f"Pending contradictions after Turn 1: {pending}")

    # 3. Test Low Importance Contradiction (Emotional state update)
    print("\n[Turn 2] User says: 'Actually I feel pretty tired right now.'")
    await consolidator.consolidate(
        DEFAULT_USER_ID,
        "Actually I feel pretty tired right now.",
        "I understand, get some rest!"
    )

    nodes_now = store.get_all_nodes(DEFAULT_USER_ID)
    print(f"Updated emotion state node: {nodes_now.get('emotions:state')}")
    print(f"Career company node (held for confirmation): {nodes_now.get('career:company')}")
    
    print("\n--- Test Complete ---")

if __name__ == "__main__":
    asyncio.run(run_test())
