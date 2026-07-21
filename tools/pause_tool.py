"""
tools/pause_tool.py — Sadaf Jarvis Pause / Hold On Tool

Returns a special flag to tell main.py to enter a "paused" listening mode.
"""

import json
from groq_proxy import groq_proxy
from config import CHAT_MODEL, PRIORITY_AGENT

def pause_listening(query: str = "") -> str:
    """Return a special string to enter paused mode."""
    # main.py will look for this exact string to trigger paused_mode
    return "__PAUSE_MODE_TRIGGER__"

async def should_resume(user_text: str) -> bool:
    """Agentic check if the user wants to resume interaction with Sadaf."""
    resume_prompt = (
        "You are evaluating if a user utterance should wake or resume speaking to a voice assistant named Sadaf.\n"
        "The user text could be a greeting, addressing the assistant, a question, a continuation of their thoughts, or speaking aloud.\n"
        "Output valid JSON.\n"
        "Rules:\n"
        "- Return JSON: {\"resume\": true} if the user is addressing the AI, resuming conversation, asking a question, or speaking to the system.\n"
        "- Return JSON: {\"resume\": false} ONLY if the user is explicitly speaking to a third person offline or telling someone else to ignore the AI.\n"
        "When in doubt, output JSON: {\"resume\": true}."
    )
    try:
        raw_resume = await groq_proxy.call(
            model=CHAT_MODEL,
            messages=[
                {"role": "system", "content": resume_prompt},
                {"role": "user", "content": user_text},
            ],
            priority=PRIORITY_AGENT,
            temperature=0.0,
            max_tokens=30,
            response_format={"type": "json_object"},
        )
        parsed_resume = json.loads(raw_resume)
        return parsed_resume.get("resume", True) is True
    except Exception as e:
        print(f"[Pause Check] Error: {e}")
        return True
