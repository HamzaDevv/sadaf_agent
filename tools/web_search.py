"""
tools/web_search.py — Sadaf Jarvis Web Search Tool

Uses Tavily (AI-optimized) as primary search engine.
Compresses results into 2 spoken sentences via Groq proxy.
"""
import asyncio
import requests
from config import TAVILY_API_KEY
from groq_proxy import groq_proxy
from config import CHAT_MODEL


async def _compress_search_results(query: str, results_text: str) -> str:
    """Compress raw search results into a 1-2 sentence spoken answer."""
    result = await groq_proxy.call(
        model=CHAT_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a voice assistant. Summarize the following search results "
                    "into a direct, spoken-English answer of 1-2 sentences max. "
                    "Be natural and conversational. No markdown, no bullet points, no lists."
                ),
            },
            {
                "role": "user",
                "content": f"User asked: '{query}'\n\nSearch results:\n{results_text}",
            },
        ],
        temperature=0.3,
        max_tokens=100,
    )
    return result or "I couldn't find a clear answer for that."


def _tavily_search(query: str) -> str:
    """Call Tavily Search API and return a raw text summary."""
    if not TAVILY_API_KEY:
        return ""
    try:
        resp = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key": TAVILY_API_KEY,
                "query": query,
                "search_depth": "basic",
                "max_results": 3,
                "include_answer": True,
            },
            timeout=8,
        )
        data = resp.json()
        # Use Tavily's built-in AI answer if available
        if data.get("answer"):
            return data["answer"]
        # Otherwise build from results
        results = data.get("results", [])
        if not results:
            return ""
        snippets = [r.get("content", "") for r in results[:3] if r.get("content")]
        return "\n".join(snippets)
    except Exception as e:
        return ""


async def web_search(query: str) -> str:
    """Search the web and return a spoken-English answer."""
    raw = await asyncio.to_thread(_tavily_search, query)
    if not raw:
        return "I couldn't find anything useful on that right now."
    return await _compress_search_results(query, raw)
