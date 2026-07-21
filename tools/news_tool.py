"""
tools/news_tool.py — Sadaf Jarvis News Tool

Fetches top headlines via GNews API (free tier).
Returns spoken-English summary of top 3 headlines.
"""
import asyncio
import requests
from config import GNEWS_API_KEY

GNEWS_BASE = "https://gnews.io/api/v4"


def _fetch_headlines(topic: str = None) -> list[dict]:
    """Fetch top headlines from GNews. Optionally filter by topic keyword."""
    if not GNEWS_API_KEY:
        return []
    try:
        if topic:
            url = f"{GNEWS_BASE}/search"
            params = {
                "q": topic,
                "lang": "en",
                "max": 3,
                "apikey": GNEWS_API_KEY,
                "sortby": "publishedAt",
            }
        else:
            url = f"{GNEWS_BASE}/top-headlines"
            params = {
                "lang": "en",
                "max": 3,
                "apikey": GNEWS_API_KEY,
            }
        resp = requests.get(url, params=params, timeout=6)
        return resp.json().get("articles", [])
    except Exception:
        return []


async def get_news(query: str = "") -> str:
    """
    Return a spoken-English summary of the latest news.
    If query contains a topic (e.g. 'tech news', 'cricket news'), filter by it.
    """
    # Extract topic keyword from query
    topic = None
    query_lower = query.lower()
    for keyword in ["about", "on", "regarding", "for"]:
        if keyword in query_lower:
            topic = query_lower.split(keyword, 1)[-1].strip()
            break
    # Also check direct topic words (e.g. "tech news", "sports news")
    if not topic:
        known_topics = ["tech", "sports", "cricket", "politics", "ai", "business",
                        "science", "health", "entertainment", "world"]
        for t in known_topics:
            if t in query_lower:
                topic = t
                break

    articles = await asyncio.to_thread(_fetch_headlines, topic)
    if not articles:
        return "I couldn't fetch the latest news right now."

    output = "Latest News Headlines:\n\n"
    for i, a in enumerate(articles, 1):
        output += f"{i}. {a.get('title', 'Headline')}\n   URL: {a.get('url', '')}\n   Snippet: {a.get('description', '')}\n\n"
        
    return output
