"""
tools/pause_tool.py — Sadaf Jarvis Pause / Hold On Tool

Returns a special flag to tell main.py to enter a "paused" listening mode.

Resume logic (should_resume):
  Stage 1 — Strict regex: Wakes when user says the AI name paired with a
             clear resumption keyword/greeting, OR when user uses a direct 
             resumption phrase like "I am back" or "let's continue".
             This prevents side-conversations from accidentally triggering the wake.
  Stage 2 — LLM fallback: only used when the AI name appears but no keyword is
             found (ambiguous case). LLM must be STRICT — default is False.

Wake examples  : "Sadaf", "hey Sadaf", "Sadaf I'm back", "I am back", "wake up"
Ignore examples: "А как тут, Карат?" (Russian side-talk), "bro wait", "yeah"
"""

import re
import json
from llm_proxy import llm_proxy
from config import CHAT_MODEL, PRIORITY_AGENT, AI_NAME


def pause_listening(query: str = "") -> str:
    """Return a special string to enter paused mode."""
    # main.py will look for this exact string to trigger paused_mode
    return "__PAUSE_MODE_TRIGGER__"


# ── Stage 1: Strict wake-word regex ──────────────────────────────────────────
# Must contain the AI name AND at least one resumption signal.
# We compile once at import time for speed.

_AI = re.escape(AI_NAME.lower())   # e.g. "sadaf"

# Pattern: AI name (with optional filler) + resumption keyword
# OR: a direct greeting/call like "hey sadaf", "okay sadaf", "sadaf!"
_RESUME_STRICT = re.compile(
    r"(?:"
    # Direct address: "hey/okay/hi sadaf", "sadaf!" (name at end or alone)
    r"(?:^|\W)(?:hey|hi|okay|ok|yo|alright)\s+" + _AI + r"(?:\W|$)"
    r"|"
    # Name alone or as single utterance: "sadaf" / "sadaf."
    r"(?:^|\W)" + _AI + r"(?:[!?.\s]*$)"
    r"|"
    # Name + resumption keyword nearby (within same sentence)
    r"(?:^|\W)" + _AI + r"(?:\W+\w+){0,5}\W*"
    r"(?:back|ready|here|continue|resume|I'm back|let's go|go ahead|listening|done)"
    r"|"
    r"(?:back|ready|here|continue|resume|I'm back|let's go|go ahead|listening|done)"
    r"(?:\W+\w+){0,5}\W*" + _AI + r"(?:\W|$)"
    r"|"
    # Easy resumption without name
    r"(?:^|\W)(?:i'm back|i am back|i'm ready|i am ready|wake up|let's continue|let's resume)(?:\W|$)"
    r")",
    re.IGNORECASE,
)

# Name appears but no clear keyword → ambiguous, escalate to LLM
_NAME_PRESENT = re.compile(
    r"(?:^|\W)" + _AI + r"(?:\W|$)",
    re.IGNORECASE,
)

_STRICT_RESUME_PROMPT = (
    f"You are a wake-word validator for a paused voice assistant named {AI_NAME}.\n"
    f"The assistant is PAUSED and should ONLY resume if the user is DIRECTLY and "
    f"UNAMBIGUOUSLY addressing {AI_NAME} to resume/come back.\n"
    f"Do NOT resume for: side-conversations, talking to other people, mentioning "
    f"{AI_NAME} in passing, or any utterance that does not clearly call the assistant back.\n"
    f"When in doubt → do NOT resume.\n"
    f"Output ONLY valid JSON: {{\"resume\": true}} or {{\"resume\": false}}"
)


async def should_resume(user_text: str) -> bool:
    """
    Two-stage resume check.

    Stage 1 — regex: fast, zero-cost, very strict.
      - Match → True (wake immediately, no LLM needed)
      - No AI name → False (definitely side-talk, skip)
      - Name present but no keyword → go to Stage 2

    Stage 2 — LLM: strict prompt, default False.
    """
    text_lower = user_text.strip()

    # Stage 1a: strict regex match — wake immediately
    if _RESUME_STRICT.search(text_lower):
        print(f"[PauseTool] Stage-1 wake detected: '{user_text}'")
        return True

    # Stage 1b: AI name not mentioned at all → definitely side-talk, skip LLM
    if not _NAME_PRESENT.search(text_lower):
        return False

    # Stage 2: name is present but no clear resumption keyword → ask LLM
    print(f"[PauseTool] Ambiguous wake — escalating to LLM: '{user_text}'")
    try:
        raw_resume = await llm_proxy.call(
            model=CHAT_MODEL,
            messages=[
                {"role": "system", "content": _STRICT_RESUME_PROMPT},
                {"role": "user", "content": user_text},
            ],
            priority=PRIORITY_AGENT,
            temperature=0.0,
            max_tokens=15,
            response_format={"type": "json_object"},
        )
        parsed_resume = json.loads(raw_resume)
        result = parsed_resume.get("resume", False) is True
        print(f"[PauseTool] LLM resume decision: {result}")
        return result
    except Exception as e:
        print(f"[PauseTool] LLM error during resume check: {e}")
        # Default to NOT resuming to avoid false positives
        return False
