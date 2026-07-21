"""
main.py — Sadaf V6 (Antigravity 2.0 Agent-First Architecture)

V6 changes:
  - Boss Orchestrator coordinates specialized subagents
  - Tool Subagent handles complex tool chains and clipboard auto-save
  - Speaker Subagent unifies personality and TTS
  - Memory Subagent strictly isolates user facts from AI context
"""
import asyncio
import time
from collections import deque

from audio.listen import listen_once, transcribe_with_noise_reduction
from audio.speak import speak_async_system

from brain.orchestrator import BossOrchestrator
from brain.speaker_agent import SpeakerSubagent
from tools.tool_subagent import ToolSubagent

from memory.graph_store import MemoryGraphStore
from memory.memory_agent import MemoryAgent
from memory.consolidator import MemoryConsolidator

from brain.pre_processor import analyze_input
from tools.reminder import fire_pending_reminders
from tools.timer_tool import set_speak_fn as timer_set_speak_fn
from tools.pause_tool import should_resume

from config import (
    AI_NAME,
    MEMORY_DIR,
    DEFAULT_USER_ID,
    RECORDING_TIME_IN_SECONDS,
    OUTPUT_FILE,
    PRIVACY_MODE,
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
    
    tool_subagent = ToolSubagent()
    speaker_subagent = SpeakerSubagent()
    
    orchestrator = BossOrchestrator(
        memory_agent=agent,
        tool_subagent=tool_subagent,
        speaker_subagent=speaker_subagent,
        consolidator=consolidator
    )

    graph_store.ensure_user_dir(DEFAULT_USER_ID)
    graph_store.increment_conversation_count(DEFAULT_USER_ID)

    # ── Wire callbacks ───────────────────────────────────────────────────────
    timer_set_speak_fn(speak_async_system)
    asyncio.create_task(fire_pending_reminders(speak_async_system))

    # ── Greeting ─────────────────────────────────────────────────────────────
    await speak_async_system(f"Hey, I'm {AI_NAME}. I'm listening.")

    session_start = time.time()
    running = True

    _paused_mode = False
    _awaiting_camera_permission = False
    _pending_camera_query = ""

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

            # 2. Cognitive Pre-Processing
            analysis = await analyze_input(user_text)
            clean_text = analysis["clean_text"]
            intent = analysis["intent"]
            emotion = analysis["emotion"]

            # 3. Fast-Path Overrides (Exit/Pause)
            if intent == "exit":
                await speak_async_system("Alright, take care. Allah hafiz.")
                await save_transcript(f"User: {clean_text}")
                running = False
                break

            if intent == "pause":
                _paused_mode = True
                await speak_async_system("Alright, I'll be right here. Just say 'Sadaf' when you're ready.")
                await save_transcript(f"User: {clean_text}")
                continue
                
            if _paused_mode:
                if await should_resume(clean_text):
                    _paused_mode = False
                    await speak_async_system("I'm back!")
                    await save_transcript("Sadaf: I'm back!")
                else:
                    continue

            await save_transcript(f"User: {clean_text}")
            
            # PRIVACY_MODE camera gate (legacy check, can also be handled by subagent if upgraded later)
            if _awaiting_camera_permission:
                _awaiting_camera_permission = False
                answer = clean_text.lower()
                if any(w in answer for w in ["yes", "sure", "okay", "ok", "go ahead", "please"]):
                    from brain.vision import analyze_scene
                    vision_answer = await analyze_scene(_pending_camera_query)
                    print(f"Sadaf: {vision_answer}")
                    await speak_async_system(vision_answer)
                    await save_transcript(f"Sadaf: {vision_answer}")
                    asyncio.create_task(
                        consolidator.consolidate(DEFAULT_USER_ID, _pending_camera_query, vision_answer)
                    )
                else:
                    await speak_async_system("Alright, no worries.")
                _pending_camera_query = ""
                continue
                
            # Intercept camera requests if privacy mode is on
            if PRIVACY_MODE and any(w in clean_text.lower() for w in ["look at", "what am i holding", "take a picture"]):
                await speak_async_system("May I use the camera to take a look?")
                _awaiting_camera_permission = True
                _pending_camera_query = clean_text
                continue

            # 4. Boss Orchestrator Processing
            final_spoken = await orchestrator.process(
                user_id=DEFAULT_USER_ID,
                user_text=clean_text,
                emotion=emotion,
                intent=intent
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
