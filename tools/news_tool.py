"""
tools/news_tool.py — Sadaf Personalized News Tool

Personalization logic:
  1. If the user explicitly mentions a topic (e.g. "cricket news", "news about AI"),
     use that as the search query (highest priority).
  2. Otherwise, extract the user's interests from the memory context string that is
     passed in, and pick the most relevant category.
  3. Fall back to general top headlines if no interests found.

Output: a natural, spoken-English summary — no bullet points, no URLs, no headlines
dumped verbatim. Reads like a friend catching you up on the news.
"""

import asyncio
import re
import requests
from llm_proxy import llm_proxy
from config import GNEWS_API_KEY, SUBAGENT_MODEL, PRIORITY_AGENT

GNEWS_BASE = "https://gnews.io/api/v4"

# ── Interest → GNews category/query map ──────────────────────────────────────
_INTEREST_MAP = {
    # tech / coding
    "tech": "technology",
    "technology": "technology",
    "coding": "technology",
    "programming": "technology",
    "software": "technology",
    "ai": "artificial intelligence",
    "machine learning": "artificial intelligence",
    # sports
    "sports": "sports",
    "cricket": "cricket",
    "football": "football",
    "soccer": "football",
    "basketball": "basketball",
    "tennis": "tennis",
    # entertainment
    "movies": "entertainment",
    "cinema": "entertainment",
    "entertainment": "entertainment",
    "music": "music",
    "gaming": "gaming",
    # business / finance
    "business": "business",
    "finance": "finance",
    "stock": "stock market",
    "economy": "economy",
    # world / politics
    "politics": "politics",
    "world": "world news",
    # science / health
    "science": "science",
    "health": "health",
    "fitness": "fitness",
    "food": "food",
}


def _fetch_articles(query: str = None, max_results: int = 4) -> list[dict]:
    """Fetch articles from GNews. Uses search endpoint when query given, else top-headlines."""
    if not GNEWS_API_KEY:
        return []
    try:
        if query:
            url = f"{GNEWS_BASE}/search"
            params = {
                "q": query,
                "lang": "en",
                "max": max_results,
                "apikey": GNEWS_API_KEY,
                "sortby": "publishedAt",
            }
        else:
            url = f"{GNEWS_BASE}/top-headlines"
            params = {
                "lang": "en",
                "max": max_results,
                "apikey": GNEWS_API_KEY,
            }
        resp = requests.get(url, params=params, timeout=8)
        if resp.status_code != 200:
            print(f"[NewsTool] HTTP Error {resp.status_code}: {resp.text}")
        return resp.json().get("articles", [])
    except Exception as e:
        print(f"[NewsTool] Exception in _fetch_articles: {e}")
        return []


_CONVERSATIONAL_STOP_WORDS = {
    "hello", "hi", "hey", "can", "could", "would", "please", "tell", "me", "give", "get", "find",
    "what", "is", "are", "there", "any", "some", "the", "a", "an", "latest", "recent", "interesting",
    "good", "bad", "today", "now", "happened", "happen", "news", "updates", "update", "this", "week",
    "month", "show", "read", "know", "about", "for", "on", "regarding", "you", "your", "yours", "i",
    "my", "we", "our"
}



def _extract_explicit_topic(query: str) -> str | None:
    """
    Return an explicit topic if the user named one in their request.
    e.g. "latest news about cricket" → "cricket"
         "tech news" → "technology"
         "news" → None
    """
    if not query:
        return None

    q_lower = query.lower()

    # 1. Look for explicit preposition patterns first: "news about cricket", "news regarding AI"
    for prep in ["about", "regarding"]:
        m = re.search(r"\b" + prep + r"\b\s+(.+)", q_lower)
        if m:
            raw_target = m.group(1)
            clean_target = re.sub(r"[^\w\s]", " ", raw_target)
            words = [w for w in clean_target.split() if w not in {"today", "now", "recently", "this", "week", "month"}]
            if words:
                topic = " ".join(words[:4]).strip()
                if len(topic) >= 2:
                    return topic

    # 2. Look for specific non-conversational topic keywords before/around "news"
    clean_q = re.sub(r"[^\w\s]", " ", q_lower)
    words = [w for w in clean_q.split() if w not in _CONVERSATIONAL_STOP_WORDS]

    if words:
        topic = " ".join(words[:3]).strip()
        if len(topic) >= 2:
            return topic

    return None


def _pick_interest_query(memory_context: str) -> str | None:
    """
    Scan the memory context string for known interest keywords and return
    the best GNews search query, or None if nothing found.
    """
    if not memory_context:
        return None
    ctx_lower = memory_context.lower()
    # Score each interest by how many times its keyword appears
    scores: dict[str, int] = {}
    for keyword, gnews_query in _INTEREST_MAP.items():
        count = ctx_lower.count(keyword)
        if count:
            scores[gnews_query] = scores.get(gnews_query, 0) + count
    if not scores:
        return None
    # Pick the highest-scoring interest
    best = max(scores, key=scores.get)
    return best


_NARRATOR_PROMPT = """\
You are Sadaf, a friendly AI assistant. Your job is to summarize these news headlines \
as if you're a knowledgeable friend catching someone up on the news over a quick chat.

Rules:
- Be conversational and warm — like texting a friend, not a news anchor.
- Pick the 2-3 most interesting/important stories.
- One natural sentence per story, no bullet points, no numbering, no URLs.
- Keep the total response under 80 words.
- Don't use the word "headline" or "article" — just talk naturally.
- Reference the user's name "{user_name}" once at the start to make it personal.
- Start with a brief intro like "So {user_name}, here's what's going on..." or similar.

News data:
{news_data}
"""


async def get_news(query: str = "", memory_context: str = "", user_name: str = "there") -> str:
    """
    Return a spoken-English, conversational news summary.

    Args:
        query:          The full synthesized intent (e.g. "Get me cricket news").
        memory_context: The user's memory context string (used to extract interests).
        user_name:      The user's first name for personalization.
    """
    # 1. Determine search query
    explicit = _extract_explicit_topic(query)
    if explicit:
        search_query = explicit
        source_label = f"'{explicit}'"
    else:
        interest_query = _pick_interest_query(memory_context)
        if interest_query:
            search_query = interest_query
            source_label = f"'{interest_query}' (based on your interests)"
        else:
            search_query = None
            source_label = "top headlines"

    # 2. Fetch articles
    articles = await asyncio.to_thread(_fetch_articles, search_query, 4)
    if not articles:
        return "I couldn't pull up any news right now. My news source might be taking a break."

    # 3. Build raw news string for the LLM
    news_lines = []
    for a in articles:
        title = a.get("title", "").strip()
        desc  = a.get("description", "").strip()
        if title:
            news_lines.append(f"- {title}. {desc}" if desc else f"- {title}")
    news_data = "\n".join(news_lines)

    # 4. Ask LLM to narrate conversationally
    prompt = _NARRATOR_PROMPT.format(
        user_name=user_name,
        news_data=news_data,
    )
    try:
        narrated = await llm_proxy.call(
            model=SUBAGENT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            priority=PRIORITY_AGENT,
            temperature=0.7,
            max_tokens=500,
        )
        if narrated and len(narrated.strip()) > 10:
            return narrated.strip()
    except Exception:
        pass

    # 5. Fallback: plain conversational summary without LLM
    top = articles[:2]
    parts = [f"Here's what's in the news for you, {user_name}."]
    for a in top:
        t = a.get("title", "").strip()
        if t:
            parts.append(t + ".")
    return " ".join(parts)
