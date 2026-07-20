"""
memory/extractor.py — Sadaf V4 Fast Structured Fact Extraction

V4 changes:
  - Fact format uses "file" (filename) instead of "section" (section path)
  - Uses groq_proxy instead of direct AsyncGroq client
  - Model: llama-3.1-8b-instant (unchanged — fast, structured JSON)

Each conversation turn is analyzed and facts extracted as:
  {"file": "career.md", "key": "Job Title", "value": "Engineer"}

This maps directly to MemoryFileStore.write_key(user_id, file, key, value).
"""
import asyncio
import json
from groq_proxy import groq_proxy
from config import CHAT_MODEL, PRIORITY_EXTRACTION

EXTRACTION_PROMPT = """\
You are a memory extraction engine for a personal AI assistant named Sadaf.
Analyze the conversation interaction and extract structured facts about the user
to save into long-term memory files.

Available memory files and what they store:
- identity.md   → Full Name, Nickname, Age, Location, Language Preference
- career.md     → Job Title, Company, Job Start Date, Colleagues, Salary
- education.md  → College, Degree, Graduation Year, Courses
- family.md     → Family Members, Relationship Status, Partner Name
- health.md     → Sleep Pattern, Diet, Exercise, Health Issues, Energy Level
- interests.md  → Hobbies, Games, Music, Movies, Books, Sports, Food Preferences
- goals.md      → Short-term Goals, Long-term Goals, Current Plans
- behavior.md   → Communication Style, Humor Level, Preferred Topics, Things They Dislike
- emotions.md   → Current Emotional State, Stress Triggers, What Cheers Them Up, Sensitive Topics

Output ONLY valid JSON (no explanation, no markdown fences):
{
  "facts": [
    {"file": "career.md", "key": "Job Title", "value": "Software Engineer"}
  ],
  "emotional_state": "excited",
  "session_note": "User mentioned starting their new job on July 24."
}

Rules:
- CRITICAL: Only extract facts EXPLICITLY stated in the interaction. Do NOT infer or invent.
- CRITICAL: NEVER write "Unknown", "null", or "not explicitly stated" as a value. If a fact is not stated, simply DO NOT extract a JSON object for it. Omit it entirely.
- If no new facts found: {"facts": [], "emotional_state": null, "session_note": null}
- session_note: 1 sentence maximum summarizing the key event of this turn.
- emotional_state: one of: happy, excited, sad, frustrated, neutral, anxious, calm, tired, angry, nervous
- Do NOT extract trivial conversational filler (e.g., "User said hello").
"""


async def extract_facts(user_input: str, ai_response: str) -> dict:
    """
    Extract structured facts from a conversation turn via groq_proxy.
    Returns a patch dict or empty dict on failure.
    """
    interaction = f"User: {user_input}\nAI: {ai_response}"
    try:
        raw = await groq_proxy.call(
            model=CHAT_MODEL,
            messages=[
                {"role": "system", "content": EXTRACTION_PROMPT},
                {"role": "user",   "content": interaction},
            ],
            priority=PRIORITY_EXTRACTION,
            temperature=0.0,
            max_tokens=400,
            response_format={"type": "json_object"},
        )
        if not raw:
            return {"facts": [], "emotional_state": None, "session_note": None}
        patch = json.loads(raw)
        return patch
    except (json.JSONDecodeError, Exception) as e:
        print(f"[Extractor] Failed to extract facts: {e}")
        return {"facts": [], "emotional_state": None, "session_note": None}
