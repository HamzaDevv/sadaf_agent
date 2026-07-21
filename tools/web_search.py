"""
tools/web_search.py — Sadaf Jarvis Web Search Tool

Uses Tavily (AI-optimized) as primary search engine.
"""
import asyncio
import requests
from config import TAVILY_API_KEY
import urllib.parse
from bs4 import BeautifulSoup

def _tavily_search(query: str) -> str:
    """Call Tavily Search API and return a raw text summary including URLs."""
    if not TAVILY_API_KEY:
        return ""
    try:
        resp = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key": TAVILY_API_KEY,
                "query": query,
                "search_depth": "basic",
                "max_results": 4,
                "include_answer": True,
            },
            timeout=8,
        )
        data = resp.json()
        
        output = ""
        if data.get("answer"):
            output += f"Summary: {data['answer']}\n\n"
            
        results = data.get("results", [])
        if results:
            output += "Sources:\n"
            for i, r in enumerate(results, 1):
                output += f"{i}. {r.get('title', 'Link')}\n   URL: {r.get('url', '')}\n   Snippet: {r.get('content', '')}\n\n"
        return output
    except Exception as e:
        print(f"[WebSearch] error: {e}")
        return ""

def _duckduckgo_search(query: str) -> str:
    """Fallback search using DuckDuckGo HTML parsing (no API key needed)."""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
        url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
        resp = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(resp.text, "html.parser")
        
        results = []
        for a in soup.find_all("a", class_="result__url", limit=4):
            link = a.get("href", "")
            if link.startswith("//duckduckgo.com/l/?uddg="):
                link = urllib.parse.unquote(link.split("uddg=")[1].split("&")[0])
            snippet_node = a.find_parent("div", class_="result").find("a", class_="result__snippet")
            snippet = snippet_node.text if snippet_node else ""
            results.append(f"- URL: {link}\n  Snippet: {snippet}")
            
        if not results:
            return "No results found."
        return "\n\n".join(results)
    except Exception as e:
        print(f"[DuckDuckGo] error: {e}")
        return "Search failed."

async def web_search(query: str, *args, **kwargs) -> str:
    """Searches the web for facts, returns raw text with links."""
    # Strip any common phrases
    q = query.lower().replace("search for", "").replace("google", "").strip()
    
    # 1. Try Tavily (best)
    result = await asyncio.to_thread(_tavily_search, q)
    if result:
        return result
        
    # 2. Fallback to DDG
    result = await asyncio.to_thread(_duckduckgo_search, q)
    return result

async def read_web_link(url: str, *args, **kwargs) -> str:
    """Reads the text content of a given URL."""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
        resp = await asyncio.to_thread(requests.get, url, headers=headers, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
        
        # Kill javascript and style tags
        for script in soup(["script", "style"]):
            script.extract()
            
        text = soup.get_text(separator='\n')
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = '\n'.join(chunk for chunk in chunks if chunk)
        
        # Limit to first 10,000 characters to save tokens
        return text[:10000]
    except Exception as e:
        return f"Failed to read link: {e}"
