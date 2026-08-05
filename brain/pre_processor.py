"""
brain/pre_processor.py — Sadaf Three-Level Intent Pre-Processor

Level 0 — Fast-path for high-confidence regex intents (exit / pause):
          These simple keyword intents are detected by regex without an LLM call,
          saving 1-2 seconds of round-trip latency per turn.
          The keywords are phonetically distinctive, so STT rarely corrupts them.

Level 1 — Regex fast-detect: classifies other obvious intent categories WITHOUT an LLM call.

Level 2 — LLM confirm + clean: runs for ambiguous/complex inputs to (a) verify the
          regex classification and (b) fix STT noise / homophone errors in the text.

Why three levels?
  - Level 0 eliminates LLM latency entirely for stop/pause/exit — most frequent
    short utterances. Users notice this delay most acutely on these short commands.
  - Level 1 reduces LLM token budget by telling it "we think this is X".
  - Level 2 handles everything else: corrects false positives and cleans STT output.
  - Together: ~50% fewer LLM calls vs pure-LLM approach.
"""

import re
import json
from groq_proxy import groq_proxy
from config import SUBAGENT_MODEL, PRIORITY_AGENT, PRE_PROCESSOR_TWO_LEVEL

# ── Level 1: Regex Intent Patterns ────────────────────────────────────────────
# These are intentionally broad — false positives are acceptable because Level 2
# (LLM) will correct them. Patterns are case-insensitive.

_EXIT_PATTERNS = re.compile(
    r"\b(bye|goodbye|good bye|see you|quit|exit|shut ?down|that'?s? all|done for (now|today))\b",
    re.IGNORECASE,
)
_PAUSE_PATTERNS = re.compile(
    r"\b(wait|hold on|hold up|one (sec|second|moment)|pause|stop|just a (sec|second|moment))\b",
    re.IGNORECASE,
)
_VISION_PATTERNS = re.compile(
    r"\b(look at (this|that)|what (am i|is this|do you see)|can you see|what'?s? in front|"
    r"take a look|use (the )?camera|describe (this|what you see)|show me what)\b",
    re.IGNORECASE,
)

# Level-0 fast-path: exit / pause are so distinctive that STT rarely corrupts
# them, and we never need LLM cleanup. Short-circuit immediately.
_FAST_PATH_INTENTS = {"exit", "pause"}


def _regex_classify(text: str) -> str | None:
    """
    Returns a hint intent string if regex is confident, else None (LLM decides).
    None means 'converse or unclear' — LLM will figure it out.
    """
    t = text.strip()
    if _EXIT_PATTERNS.search(t):
        return "exit"
    if _PAUSE_PATTERNS.search(t):
        return "pause"
    if _VISION_PATTERNS.search(t):
        return "vision_query"
    return None  # LLM decides


# ── Level 2: LLM Prompt ───────────────────────────────────────────────────────
# The hint tells the LLM what regex already suspects. It confirms or overrides.

PRE_PROCESSOR_PROMPT = """\
You are the STT cleaner and intent validator for Sadaf, an AI voice assistant.

Tasks:
1. "clean_text": Fix STT (speech-to-text) errors:
   - Correct spelling/homophone errors based on context.
   - Strip nonsensical, disconnected mid-sentence fragments that are clearly STT
     garbage (e.g. "I live on 35 Ashoka Colony and I'm not going to die" — the
     second clause is noise; keep only "I live on 35 Ashoka Colony").
   - Preserve ALL meaningful content. Do NOT paraphrase or shorten intent.

2. "intent": Confirm or correct the hint intent. Choose strictly from:
   - "exit"       : user explicitly ending interaction ("bye", "goodbye", "quit")
   - "pause"      : user wants Sadaf to hold on ("wait", "hold on", "one sec")
   - "vision_query": user wants camera ("what am I holding", "look at this")
   - "converse"   : everything else — questions, commands, conversation

   HINT from regex (may be wrong — override if the actual text says otherwise): {hint}

3. "emotion": Apparent emotion ("neutral", "happy", "frustrated", "sad", "rushed", "excited").

Output ONLY valid JSON:
{{
  "clean_text": "...",
  "intent": "converse",
  "emotion": "neutral"
}}
"""


# ── Main Entry Point ──────────────────────────────────────────────────────────

async def analyze_input(raw_text: str) -> dict:
    """
    Three-level pre-processor.
    Level 0: fast-path for exit/pause — skip LLM entirely (saves 1-2s latency).
    Level 1: regex classifies intent (fast, no tokens).
    Level 2: LLM confirms + cleans text (runs for all non-fast-path inputs).
    Returns: {"clean_text": str, "intent": str, "emotion": str}
    """
    # Level 0 — fast-path: exit / pause are high-confidence, skip LLM
    hint = _regex_classify(raw_text)
    if hint in _FAST_PATH_INTENTS:
        return {
            "clean_text": raw_text.strip(),
            "intent": hint,
            "emotion": "neutral",
        }

    hint_label = hint if hint else "converse (no strong signal)"

    # Level 2 — LLM confirmation + STT cleanup
    try:
        raw_response = await groq_proxy.call(
            model=SUBAGENT_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": PRE_PROCESSOR_PROMPT.format(hint=hint_label),
                },
                {"role": "user", "content": f"RAW INPUT: {raw_text}"},
            ],
            priority=PRIORITY_AGENT,
            temperature=0.0,
            max_tokens=150,
            response_format={"type": "json_object"},
        )

        if not raw_response:
            # LLM failed — fall back to regex hint or default
            return {
                "clean_text": raw_text,
                "intent": hint or "converse",
                "emotion": "neutral",
            }

        result = json.loads(raw_response)

        clean_text = result.get("clean_text", raw_text)
        intent = result.get("intent", "converse").lower()
        emotion = result.get("emotion", "neutral").lower()

        # Sanity-check intent value
        valid_intents = {"exit", "pause", "vision_query", "converse"}
        if intent not in valid_intents:
            intent = hint or "converse"

        return {"clean_text": clean_text, "intent": intent, "emotion": emotion}

    except Exception as e:
        print(f"[PreProcessor] Error: {e}")
        return {
            "clean_text": raw_text,
            "intent": hint or "converse",
            "emotion": "neutral",
        }
