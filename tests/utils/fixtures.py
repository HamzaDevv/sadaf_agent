import os
import shutil
from typing import Tuple

from memory.graph_store import MemoryGraphStore
from memory.memory_agent import MemoryAgent
from memory.consolidator import MemoryConsolidator
from tools.tool_subagent import ToolSubagent
from brain.speaker_agent import SpeakerSubagent
from brain.orchestrator import BossOrchestrator

TEST_TEMP_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "temp_data")

def get_isolated_memory_store(run_id: str) -> MemoryGraphStore:
    """Returns an isolated MemoryGraphStore for a specific test run."""
    storage_dir = os.path.join(TEST_TEMP_DIR, run_id)
    if os.path.exists(storage_dir):
        shutil.rmtree(storage_dir)
    os.makedirs(storage_dir, exist_ok=True)
    return MemoryGraphStore(storage_dir=storage_dir)

def get_isolated_subsystems(run_id: str) -> Tuple[MemoryGraphStore, MemoryAgent, MemoryConsolidator, ToolSubagent, SpeakerSubagent]:
    """Returns a tuple of isolated memory and tool subsystems."""
    store = get_isolated_memory_store(run_id)
    agent = MemoryAgent(store)
    consolidator = MemoryConsolidator(store)
    tool_subagent = ToolSubagent()
    speaker_subagent = SpeakerSubagent()
    return store, agent, consolidator, tool_subagent, speaker_subagent

def get_isolated_orchestrator(run_id: str) -> BossOrchestrator:
    """Returns a fully wired BossOrchestrator with isolated memory."""
    _, agent, consolidator, tool, speaker = get_isolated_subsystems(run_id)
    orchestrator = BossOrchestrator(
        memory_agent=agent,
        tool_subagent=tool,
        speaker_subagent=speaker,
        consolidator=consolidator
    )
    return orchestrator

def cleanup_isolated_data(run_id: str):
    """Cleans up the temporary directory for the run_id."""
    storage_dir = os.path.join(TEST_TEMP_DIR, run_id)
    if os.path.exists(storage_dir):
        shutil.rmtree(storage_dir)
