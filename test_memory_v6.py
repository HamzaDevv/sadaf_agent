import os
import asyncio
from dotenv import load_dotenv

load_dotenv()

from memory.graph_store import MemoryGraphStore
from memory.consolidator import MemoryConsolidator

async def run_test():
    store = MemoryGraphStore(storage_dir="test_memory_data")
    consolidator = MemoryConsolidator(store)
    
    user = "test_user_v6"
    
    print("--- Turn 1: I am learning Python ---")
    await consolidator.consolidate(user, "I am learning Python and I love it.", "That's great! Python is very useful.")
    
    print("--- Turn 2: Actually, I switched to C++ ---")
    await consolidator.consolidate(user, "Actually, I switched to C++ instead of Python. I no longer use python.", "Oh, why the change?")
    
    print("--- Turn 3: I love C++ ---")
    await consolidator.consolidate(user, "I love C++ because it's fast.", "Yes, C++ is very fast.")
    
    store.visualize(user)
    print("Visualized graph to test_memory_data/test_user_v6/graph_viz.html")

if __name__ == "__main__":
    asyncio.run(run_test())
