"""
main.py — Sadaf V6 (Antigravity 2.0 Agent-First Architecture)

V6 changes:
  - Boss Orchestrator coordinates specialized subagents
  - Tool Subagent is now autonomous with clarification feedback loop
  - Speaker Subagent unifies personality and TTS
  - Memory Subagent strictly isolates user facts from AI context
  - vision_query intent fast-paths camera through orchestrator
"""
import warnings
warnings.filterwarnings("ignore", category=UserWarning, module="webrtcvad")

import asyncio
import time

from audio.listen import listen_once, transcribe_with_noise_reduction
from audio.speak import speak_async_system

from brain.orchestrator import BossOrchestrator
from brain.speaker_agent import SpeakerSubagent
from tools.tool_subagent import ToolSubagent

from memory.graph_store import MemoryGraphStore
from memory.memory_agent import MemoryAgent
from memory.consolidator import MemoryConsolidator

from brain.pre_processor import analyze_input
from brain.intent_resolver import intent_resolver
from brain.agent_core import AgentCore
from tools.reminder import fire_pending_reminders
from tools.timer_tool import set_speak_fn as timer_set_speak_fn
from tools.pause_tool import should_resume

from config import (
    AI_NAME,
    MEMORY_DIR,
    DEFAULT_USER_ID,
    RECORDING_TIME_IN_SECONDS,
    OUTPUT_FILE,
    USE_V7_ORCHESTRATOR,
)


def _sync_write_transcript(text: str):
    try:
        with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
            timestamp = time.strftime("%H:%M:%S")
            f.write(f"[{timestamp}] {text}\n")
    except Exception:
        pass


async def save_transcript(text: str):
    await asyncio.to_thread(_sync_write_transcript, text)


async def run():
    print(f"\n🤖 {AI_NAME} V6 starting — Antigravity 2.0 Agent-First Architecture\n")

    # ── Initialize subsystems ────────────────────────────────────────────────
    graph_store  = MemoryGraphStore(MEMORY_DIR)
    agent        = MemoryAgent(graph_store)
    consolidator = MemoryConsolidator(graph_store)

    # speak_fn is wired into tool_subagent so reminder/timer TTS callbacks work
    tool_subagent    = ToolSubagent(speak_fn=speak_async_system)
    speaker_subagent = SpeakerSubagent()

    orchestrator = BossOrchestrator(
        memory_agent=agent,
        tool_subagent=tool_subagent,
        speaker_subagent=speaker_subagent,
        consolidator=consolidator,
    )

    agent_core = None
    if USE_V7_ORCHESTRATOR:
        agent_core = AgentCore(
            memory_agent=agent,
            consolidator=consolidator,
            speaker_subagent=speaker_subagent
        )

    graph_store.ensure_user_dir(DEFAULT_USER_ID)
    graph_store.increment_conversation_count(DEFAULT_USER_ID)

    # ── Wire callbacks ───────────────────────────────────────────────────────
    timer_set_speak_fn(speak_async_system)
    asyncio.create_task(fire_pending_reminders(speak_async_system))

    # ── Greeting ─────────────────────────────────────────────────────────────
    # Fetch user name if available
    all_nodes = graph_store.get_all_nodes(DEFAULT_USER_ID)
    user_name = "there"
    for nid, node in all_nodes.items():
        if node.get("key") in ("name", "full_name"):
            val = node.get("value", "")
            if val and val.lower() not in ("none", ""):
                user_name = val.split()[0]
                break

    last_sessions = graph_store.get_last_n_sessions(DEFAULT_USER_ID, 1)
    if not last_sessions or "No past sessions" in last_sessions:
        greeting = f"Hey, I'm {AI_NAME}. I'm listening."
    else:
        greeting = f"Hey {user_name}, welcome back! I'm listening."

    print(f"Sadaf: {greeting}")
    await speak_async_system(greeting)

    session_start = time.time()
    running       = True
    _paused_mode  = False

    try:
        while running and (time.time() - session_start < RECORDING_TIME_IN_SECONDS):

            # 1. Listen
            audio = await listen_once()
            if audio is None:
                continue

            raw = await transcribe_with_noise_reduction(audio)
            if not raw:
                continue

            user_text = raw.split(" - ", 1)[-1].strip() if " - " in raw else raw.strip()
            if not user_text:
                continue

            # 3. Paused-mode gate — MUST run BEFORE analyze_input.
            # Reason: the LLM pre-processor strips address words like "Ok Sadaf,"
            # from utterances (e.g. "Ok Sadaf, I am back" → "I am back"), which
            # removes the AI name so the wake regex never fires.
            # Fix: while paused, skip the LLM entirely and check the raw STT text.
            if _paused_mode:
                print(f"[paused, filtered]: {user_text}")
                if await should_resume(user_text):
                    _paused_mode = False
                    print("Sadaf: I'm back!")
                    await speak_async_system("I'm back!")
                    await save_transcript("Sadaf: I'm back!")
                # Whether resumed or not, don't process this turn further.
                # Next loop iteration picks up fresh input.
                continue

            # 2. Cognitive Pre-Processing (only runs when NOT paused)
            if USE_V7_ORCHESTRATOR:
                analysis = await intent_resolver.resolve(user_text)
            else:
                analysis = await analyze_input(user_text)

            clean_text = analysis["clean_text"]
            intent     = analysis["intent"]
            emotion    = analysis["emotion"]


            # 4. Fast-Path Overrides (Exit / Pause) — only when NOT paused
            if intent == "exit":
                print("Sadaf: Alright, take care. Allah hafiz.")
                await speak_async_system("Alright, take care. Allah hafiz.")
                await save_transcript(f"User: {clean_text}")
                running = False
                break

            if intent == "pause":
                _paused_mode = True
                msg = f"Alright, I'll be right here. Just say '{AI_NAME}' when you're ready."
                print(f"Sadaf: {msg}")
                await speak_async_system(msg)
                await save_transcript(f"User: {clean_text}")
                continue

            await save_transcript(f"User: {clean_text}")

            # 4. Boss Orchestrator Processing
            # vision_query intent is handled as a fast-path inside the orchestrator.
            # All other intents (tool, speak, clarify) are also routed inside.
            if USE_V7_ORCHESTRATOR:
                final_spoken = await agent_core.process(
                    user_id=DEFAULT_USER_ID,
                    user_text=clean_text,
                    emotion=emotion,
                    intent=intent,
                )
            else:
                final_spoken = await orchestrator.process(
                    user_id=DEFAULT_USER_ID,
                    user_text=clean_text,
                    emotion=emotion,
                    intent=intent,
                )

            print(f"Sadaf: {final_spoken}")
            await speak_async_system(final_spoken)
            await save_transcript(f"Sadaf: {final_spoken}")

    except KeyboardInterrupt:
        print(f"\n\n[Ctrl+C] Shutting down {AI_NAME}...")
    finally:
        print(f"\n📝 Session saved to {MEMORY_DIR}/{DEFAULT_USER_ID}/")


if __name__ == "__main__":
    asyncio.run(run())
