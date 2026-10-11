"""
brain/intent_resolver.py — Sadaf V7 Intent Resolver (3-Tier)

Tier 1: Regex fast-path for stop/pause/exit (zero latency).
Tier 2: Groq JSON extraction for intent & STT cleanup with a strict 2-second timeout.
Tier 3: Handled by AgentCore (DeepSeek) if Tier 2 detects a complex tool/converse scenario.
"""

import re
import json
import asyncio
from typing import Dict, Any

from llm_proxy import llm_proxy
from config import SUBAGENT_MODEL, PRIORITY_AGENT

# ── Tier 1: Regex Patterns ────────────────────────────────────────────────────

_EXIT_PATTERNS = re.compile(
    r"\b(bye|goodbye|good bye|see you|quit|exit|shut ?down|that'?s? all|done for (now|today))\b",
    re.IGNORECASE,
)
_PAUSE_PATTERNS = re.compile(
    r"\b(wait|hold on|hold up|one (sec|second|moment)|pause|stop|just a (sec|second|moment))\b",
    re.IGNORECASE,
)
_DISMISS_PATTERNS = re.compile(
    r"\b(nothing|nevermind|never mind|forget it|skip it|cancel that|ignore that)\b",
    re.IGNORECASE,
)
_VISION_PATTERNS = re.compile(
    r"\b(look at (this|that)|what (am i|is this|do you see)|can you see|what'?s? in front|"
    r"take a look|use (the )?camera|describe (this|what you see)|show me what)\b",
    re.IGNORECASE,
)

_FAST_PATH_INTENTS = {"exit", "pause", "dismiss"}


def _regex_classify(text: str) -> str | None:
    """Returns a hint intent string if regex is confident, else None."""
    t = text.strip()
    if _EXIT_PATTERNS.search(t):
        return "exit"
    if _PAUSE_PATTERNS.search(t):
        return "pause"
    if _DISMISS_PATTERNS.search(t):
        return "dismiss"
    if _VISION_PATTERNS.search(t):
        return "vision_query"
    return None


# ── Tier 2: Groq Prompt ───────────────────────────────────────────────────────

INTENT_PROMPT = """\
Resolve this user utterance into a structured intent and clean up any obvious STT noise.

1. clean_text: Fix obvious STT (speech-to-text) errors based on context. Do NOT paraphrase or shorten.
2. intent: Choose strictly from:
   - "exit"       : user ending interaction
   - "pause"      : user wants you to hold on
   - "dismiss"    : user cancels topic
   - "vision_query": user wants camera analysis
   - "tool"       : user wants to use a tool (timer, weather, news, search, app, reminder)
   - "converse"   : general chat, questions, or unclear
3. emotion: Apparent emotion (neutral, happy, frustrated, sad, rushed, excited)

Output JSON ONLY:
{{
    "clean_text": "...",
    "intent": "...",
    "emotion": "..."
}}
"""


class IntentResolver:
    async def resolve(self, raw_text: str) -> Dict[str, Any]:
        """
        Executes Tier 1 (Regex) and Tier 2 (Groq classification).
        Returns {"clean_text": str, "intent": str, "emotion": str}
        """
        hint = _regex_classify(raw_text)

        # Tier 1: Fast-path
        if hint in _FAST_PATH_INTENTS:
            return {
                "clean_text": raw_text.strip(),
                "intent": hint,
                "emotion": "neutral",
            }

        # Tier 2: Structured extraction via Groq (with strict 2s timeout)
        try:
            raw_response = await llm_proxy.call(
                model=SUBAGENT_MODEL,
                messages=[
                    {"role": "system", "content": INTENT_PROMPT},
                    {"role": "user", "content": f"RAW INPUT: {raw_text}"}
                ],
                priority=PRIORITY_AGENT,
                temperature=0.0,
                max_tokens=200,
                response_format={"type": "json_object"},
                timeout=2.0  # Strict timeout so hot-path doesn't stall
            )

            if not raw_response:
                raise ValueError("No response from Groq.")

            result = json.loads(raw_response)

            clean_text = result.get("clean_text", raw_text)
            intent = result.get("intent", "converse").lower()
            emotion = result.get("emotion", "neutral").lower()

            valid_intents = {"exit", "pause", "dismiss", "vision_query", "tool", "converse"}
            if intent not in valid_intents:
                intent = hint or "converse"

            return {"clean_text": clean_text, "intent": intent, "emotion": emotion}

        except Exception as e:
            # Fallback to Tier 3 (AgentCore handles it) on timeout or failure
            print(f"[IntentResolver] Tier 2 fallback due to: {e}")
            return {
                "clean_text": raw_text,
                "intent": hint or "converse",
                "emotion": "neutral",
            }

# Singleton instance
intent_resolver = IntentResolver()
