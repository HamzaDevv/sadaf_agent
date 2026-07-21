import json
from config import BOSS_MODEL, PRIORITY_AGENT
from groq_proxy import groq_proxy

async def score_conversation(turns: list[dict], persona: str) -> dict:
    """
    Evaluates a full conversation and returns a JSON dict with scores.
    """
    prompt = f"""You are the AI Judge for Sadaf's testing framework.
Evaluate this conversation between a Fake Human and Sadaf.

FAKE HUMAN PERSONA:
{persona}

CONVERSATION TURNS:
{json.dumps(turns, indent=2)}

Score the interaction from 1 to 10 on these rubrics:
- "relevance": Did Sadaf's replies directly address the user?
- "naturalness": Did it flow naturally (not repetitive/robotic)?
- "orchestration": Did Sadaf select tools and respond intelligently?

Output exactly this JSON:
{{
    "scores": {{
        "relevance": <1-10>,
        "naturalness": <1-10>,
        "orchestration": <1-10>
    }},
    "overall": <1-10 average>,
    "notes": "Brief reasoning"
}}
"""
    try:
        raw = await groq_proxy.call(
            model=BOSS_MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            priority=PRIORITY_AGENT,
            temperature=0.0
        )
        if not raw:
            return _default_score()
        return json.loads(raw)
    except Exception:
        return _default_score()

async def score_memory_recall(query: str, response: str, expected_facts: list) -> dict:
    """Evaluates if the response correctly recalled the expected facts."""
    prompt = f"""You are the AI Judge.
User asked: "{query}"
Sadaf responded: "{response}"
Expected facts to be present: {expected_facts}

Did Sadaf successfully recall and mention these facts?
Output exactly this JSON:
{{
    "success": true/false,
    "accuracy": <0.0 to 1.0>,
    "notes": "reasoning"
}}
"""
    try:
        raw = await groq_proxy.call(
            model=BOSS_MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            priority=PRIORITY_AGENT,
            temperature=0.0
        )
        if not raw:
            return {"success": False, "accuracy": 0.0, "notes": "Failed to judge"}
        return json.loads(raw)
    except Exception:
        return {"success": False, "accuracy": 0.0, "notes": "Failed to judge"}

async def score_tool_selection(query: str, tool_chosen: str, expected_tool: str) -> dict:
    """Simple judge for fuzzy matching tool choice intent if needed, mostly deterministic though."""
    is_correct = (tool_chosen == expected_tool)
    if expected_tool is None and tool_chosen is not None:
        is_correct = False
    return {
        "success": is_correct,
        "chosen": tool_chosen,
        "expected": expected_tool
    }

def _default_score():
    return {
        "scores": {"relevance": 0, "naturalness": 0, "orchestration": 0},
        "overall": 0,
        "notes": "Evaluation failed"
    }
