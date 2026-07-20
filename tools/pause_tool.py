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
    """Agentic check if the user wants to wake Sadaf from pause mode."""
    resume_prompt = (
        "You are evaluating if a user is trying to wake up a voice assistant that is currently paused.\n"
        "The user might say things like 'Sadaf', 'Okay Sadaf', 'I'm back', 'Resume', 'Are you there', etc.\n"
        "Return JSON: {\"resume\": true} if they are trying to wake you up, or {\"resume\": false} if they are just talking to someone else."
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
            max_tokens=20,
            response_format={"type": "json_object"},
        )
        parsed_resume = json.loads(raw_resume)
        return parsed_resume.get("resume") is True
    except Exception as e:
        print(f"[Pause Check] Error: {e}")
        return False
