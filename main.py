"""
main.py — Sadaf V5 (Jarvis Tool Suite Edition)

V5 changes:
  - Full Tool Dispatcher replacing hardcoded vision keyword matching
  - 13 new tools: web search, news, weather, datetime, reminder, countdown,
    system info, app launcher, clipboard, screenshot, volume, calculator, timer
  - Reminder persistence + startup catch-up for missed reminders
  - Jarvis-style spoken announcements before each tool action
  - PRIVACY_MODE: camera asks permission before capturing
  - Camera (brain/vision.py) is now a first-class tool in the dispatcher
"""
import asyncio
import random
import time
from collections import deque

from listen import listen_once, transcribe_with_noise_reduction
from speak import speak_async_system
from brain.llm import stream_sentences
from memory.file_store import MemoryFileStore
from memory.memory_agent import MemoryAgent
from memory.consolidator import MemoryConsolidator
from personality import build_system_prompt
from tools.dispatcher import dispatcher
from tools.reminder import fire_pending_reminders
from tools.timer_tool import set_speak_fn as timer_set_speak_fn
from config import (
    AI_NAME,
    MEMORY_DIR,
    DEFAULT_USER_ID,
    BUFFER_SIZE,
    RECORDING_TIME_IN_SECONDS,
    OUTPUT_FILE,
    PRIVACY_MODE,
)


# Exit keywords
EXIT_PHRASES = [
    "terminate", "goodbye", "bye", "allah hafiz", "اللہ حافظ",
    "see you later", "shut down", "alif", "exit",
]


def _is_exit_phrase(text: str) -> bool:
    lower = text.lower().strip()
    return any(phrase in lower for phrase in EXIT_PHRASES)


def _sync_write_transcript(text: str):
    try:
        with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
            timestamp = time.strftime("%H:%M:%S")
            f.write(f"[{timestamp}] {text}\n")
    except Exception:
        pass


async def save_transcript(text: str):
    await asyncio.to_thread(_sync_write_transcript, text)


async def stream_and_speak(system_prompt: str, user_text: str) -> str:
    """
    Stream sentences from LLM and speak each one immediately.
    Returns full response text for memory consolidation.
    Model (8b vs 70b) auto-selected by groq_proxy.ModelRouter.
    """
    no_interrupt = asyncio.Event()
    full_parts = []

    async for sentence in stream_sentences(system_prompt, user_text, no_interrupt):
        if sentence.strip():
            full_parts.append(sentence)
            await speak_async_system(sentence)
            await asyncio.sleep(random.uniform(0.08, 0.15))

    return " ".join(full_parts)


async def run():
    print(f"\n🤖 {AI_NAME} V5 starting — Jarvis Tool Suite + groq proxy\n")

    buffer: deque = deque(maxlen=BUFFER_SIZE)

    # ── Initialize memory subsystems ─────────────────────────────────────────
    file_store   = MemoryFileStore(MEMORY_DIR)
    agent        = MemoryAgent(file_store)
    consolidator = MemoryConsolidator(file_store)

    file_store.ensure_user_dir(DEFAULT_USER_ID)
    file_store.increment_conversation_count(DEFAULT_USER_ID)

    # ── Wire speak callback into tools that need it ───────────────────────────
    timer_set_speak_fn(speak_async_system)

    # ── Fire any past-due reminders from previous sessions ───────────────────
    asyncio.create_task(fire_pending_reminders(speak_async_system))

    # ── Greeting ──────────────────────────────────────────────────────────────
    await speak_async_system(f"Hey, I'm {AI_NAME}. I'm listening.")

    session_start = time.time()
    running = True

    # PRIVACY_MODE: track pending camera permission
    _awaiting_camera_permission = False
    _pending_camera_query = ""
    _paused_mode = False

    try:
        while running and (time.time() - session_start < RECORDING_TIME_IN_SECONDS):

            # ── Listen ────────────────────────────────────────────────────────
            audio = await listen_once()
            if audio is None:
                continue

            raw = await transcribe_with_noise_reduction(audio)
            if not raw:
                continue

            # Strip timestamp prefix: "HH:MM:SS - text"
            user_text = raw.split(" - ", 1)[-1].strip() if " - " in raw else raw.strip()

            if not user_text:
                continue

            # ── Exit check ────────────────────────────────────────────────────
            if _is_exit_phrase(user_text):
                await speak_async_system("Alright, take care. Allah hafiz.")
                await save_transcript(f"User: {user_text}")
                running = False
                break

            await save_transcript(f"User: {user_text}")

            # ── PRIVACY_MODE camera gate ───────────────────────────────────────
            # If we asked for permission last turn, check answer now
            if _awaiting_camera_permission:
                _awaiting_camera_permission = False
                answer = user_text.lower()
                if any(w in answer for w in ["yes", "sure", "okay", "ok", "go ahead", "please"]):
                    from brain.vision import analyze_scene
                    vision_answer = await analyze_scene(_pending_camera_query)
                    print(f"Sadaf: {vision_answer}")
                    await speak_async_system(vision_answer)
                    await save_transcript(f"Sadaf: {vision_answer}")
                    buffer.append((_pending_camera_query, vision_answer))
                    asyncio.create_task(
                        consolidator.consolidate(DEFAULT_USER_ID, _pending_camera_query, vision_answer)
                    )
                else:
                    await speak_async_system("Alright, no worries.")
                _pending_camera_query = ""
                continue

            # ── Paused Mode Check ─────────────────────────────────────────────
            if _paused_mode:
                from tools.pause_tool import should_resume
                if await should_resume(user_text):
                    _paused_mode = False
                    await speak_async_system("I'm back. What's up?")
                    await save_transcript("Sadaf: I'm back. What's up?")
                continue

            # ── Tool Dispatcher ───────────────────────────────────────────────
            match = await dispatcher.route(user_text)
            if match:
                # PRIVACY_MODE: ask permission for camera, then wait
                if PRIVACY_MODE and "take a look" in match.announcement.lower():
                    await speak_async_system(match.announcement)  # "May I use the camera?"
                    _awaiting_camera_permission = True
                    _pending_camera_query = user_text
                    continue

                # Speak Jarvis announcement (if any)
                if match.announcement:
                    print(f"Sadaf: {match.announcement}")
                    await speak_async_system(match.announcement)

                # Run the tool
                try:
                    if match.needs_speak_fn:
                        if match.is_async:
                            tool_result = await match.tool_fn(user_text, speak_fn=speak_async_system)
                        else:
                            tool_result = match.tool_fn(user_text)
                    else:
                        if match.is_async:
                            tool_result = await match.tool_fn(user_text)
                        else:
                            tool_result = match.tool_fn(user_text)
                except Exception as e:
                    tool_result = f"Something went wrong with that. {e}"

                if tool_result == "__PAUSE_MODE_TRIGGER__":
                    _paused_mode = True
                    continue

                print(f"Sadaf: {tool_result}")
                await speak_async_system(tool_result)
                await save_transcript(f"User: {user_text}")
                await save_transcript(f"Sadaf: {tool_result}")
                buffer.append((user_text, tool_result))
                asyncio.create_task(
                    consolidator.consolidate(DEFAULT_USER_ID, user_text, tool_result)
                )
                continue

            # ── Standard LLM Response ─────────────────────────────────────────
            context = await agent.build_context(DEFAULT_USER_ID, buffer, user_text)
            system_prompt = build_system_prompt(context)

            full_response = await stream_and_speak(system_prompt, user_text)

            if full_response:
                await save_transcript(f"Sadaf: {full_response}")
                buffer.append((user_text, full_response))
                asyncio.create_task(
                    consolidator.consolidate(DEFAULT_USER_ID, user_text, full_response)
                )

    except KeyboardInterrupt:
        print(f"\n\n[Ctrl+C] Shutting down {AI_NAME}...")
    finally:
        print(f"\n📝 Session saved to {MEMORY_DIR}/{DEFAULT_USER_ID}/")


if __name__ == "__main__":
    asyncio.run(run())
