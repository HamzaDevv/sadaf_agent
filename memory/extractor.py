"""
memory/extractor.py — Sadaf V6 Graph Fact, Edge & Contradiction Extraction

Extracts episodic events and semantic facts/edges.
Detects conflicts/contradictions for belief updating.
"""
import json
from groq_proxy import groq_proxy
from config import CHAT_MODEL, PRIORITY_EXTRACTION

EXTRACTION_PROMPT = """\
You are a cognitive memory extraction engine for a personal AI assistant named Sadaf.
Analyze the conversation interaction and existing user memory nodes. Extract:
1. An episodic event log (raw interaction summary with an emotion and salience score [0.0-1.0]).
2. Structured semantic facts (nodes) and relationships (edges). Assign a salience score [0.0-1.0] to each fact.
3. Identify any CONTRADICTIONS with existing facts.

Available memory sections:
- identity   → Full Name, Age, Location, Language Preference
- career     → Job Title, Company, Job Start Date, Colleagues, Salary
- education  → College, Degree, Graduation Year, Courses
- family     → Family Members, Relationship Status, Partner Name
- health     → Sleep Pattern, Diet, Exercise, Health Issues, Energy Level
- interests  → Hobbies, Games, Music, Movies, Books, Sports, Food Preferences
- goals      → Short-term Goals, Long-term Goals, Current Plans
- behavior   → Communication Style, Humor Level, Preferred Topics, Things They Dislike
- emotions   → Current Emotional State, Stress Triggers, What Cheers Them Up

Output ONLY valid JSON (no explanation, no markdown fences):
{
  "episodic_event": {
    "raw_text": "User visited Accenture office and felt excited.",
    "emotion": "excited",
    "salience": 0.8,
    "contextual_triggers": ["accenture", "office"]
  },
  "facts": [
    {"section": "career", "key": "company", "value": "Accenture", "salience": 0.9}
  ],
  "edges": [
    {"from_key": "company", "from_section": "career", "to_key": "start_date", "to_section": "career", "relation": "starts_on"}
  ],
  "contradictions": [
    {
      "node_id": "career:company",
      "existing_value": "Google",
      "new_value": "Accenture",
      "salience": 0.9
    }
  ],
  "session_note": "User mentioned starting their new job at Accenture."
}

Rules:
- CRITICAL: Only extract facts EXPLICITLY stated in the interaction. Do NOT infer or invent.
- CRITICAL: The user is speaking via a Speech-to-Text (STT) engine. Ignore obvious phonetic mishearings, garbled words, or fragmented phrases (e.g., extracting a random name like "Vince" when they meant "means"). Do NOT extract facts from broken or nonsensical sentences caused by STT errors.
- CRITICAL: Compare new facts against the provided EXISTING MEMORY FACTS.
- Contradictions: If a new fact directly contradicts an existing fact, list it in "contradictions". 
- Assign a "salience" [0.0 - 1.0] for facts and contradictions. E.g., Job/Location = 0.9, recent food/mood = 0.3.
- If no new facts found: {"episodic_event": null, "facts": [], "edges": [], "contradictions": [], "session_note": null}
"""

async def extract_facts(user_input: str, ai_response: str, existing_facts_summary: str = "") -> dict:
    """
    Extract structured episodic and semantic facts from a conversation turn via groq_proxy.
    Returns a patch dict or empty dict on failure.
    """
    interaction = f"EXISTING MEMORY FACTS:\n{existing_facts_summary or 'None'}\n\nCONVERSATION TURN:\nUser: {user_input}\nAI: {ai_response}"
    try:
        raw = await groq_proxy.call(
            model=CHAT_MODEL,
            messages=[
                {"role": "system", "content": EXTRACTION_PROMPT},
                {"role": "user",   "content": interaction},
            ],
            priority=PRIORITY_EXTRACTION,
            temperature=0.0,
            max_tokens=600,
            response_format={"type": "json_object"},
        )
        if not raw:
            return {"episodic_event": None, "facts": [], "edges": [], "contradictions": [], "session_note": None}
            
        patch = json.loads(raw)
        
        # Ensure lists exist
        if "facts" not in patch: patch["facts"] = []
        if "edges" not in patch: patch["edges"] = []
        if "contradictions" not in patch: patch["contradictions"] = []
            
        return patch
    except (json.JSONDecodeError, Exception) as e:
        print(f"[Extractor] Failed to extract facts: {e}")
        return {"episodic_event": None, "facts": [], "edges": [], "contradictions": [], "session_note": None}
