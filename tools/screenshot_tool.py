"""
tools/screenshot_tool.py — Sadaf Jarvis Screenshot Tool

Takes a screenshot and optionally analyzes it with Groq Vision.
Uses Pillow + pyautogui for capture.
"""
import asyncio
import base64
import tempfile
from pathlib import Path

import pyautogui
from PIL import Image

from groq_proxy import groq_proxy
from config import VISION_MODEL, CHAT_MODEL
from utils import strip_think_tags


def _capture_screenshot() -> str:
    """Take a full-screen screenshot and save to temp file."""
    screenshot = pyautogui.screenshot()
    # Resize to reduce token usage (keep aspect ratio, max 1280px wide)
    max_width = 1280
    if screenshot.width > max_width:
        ratio = max_width / screenshot.width
        new_size = (max_width, int(screenshot.height * ratio))
        screenshot = screenshot.resize(new_size, Image.LANCZOS)
    tmp_path = Path(tempfile.gettempdir()) / "sadaf_screenshot.jpg"
    screenshot.save(str(tmp_path), "JPEG", quality=80)
    return str(tmp_path)


def _encode_image(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


async def _analyze_screenshot(image_path: str, query: str) -> str:
    """Send screenshot to Groq Vision and get a spoken analysis."""
    b64 = await asyncio.to_thread(_encode_image, image_path)
    raw = await groq_proxy.call(
        model=VISION_MODEL,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": query or "Describe what you see on this screen briefly."},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                ],
            }
        ],
        temperature=0.3,
        max_tokens=300,
    )
    raw = strip_think_tags(raw or "")

    # Compress to spoken sentence
    result = await groq_proxy.call(
        model=CHAT_MODEL,
        messages=[
            {"role": "system", "content": "Summarize this screen analysis in 1-2 spoken sentences. No markdown."},
            {"role": "user", "content": raw},
        ],
        temperature=0.2,
        max_tokens=80,
    )
    return result or raw


async def take_screenshot(query: str = "") -> str:
    """Take a screenshot and optionally describe what's on screen."""
    try:
        image_path = await asyncio.to_thread(_capture_screenshot)
        query_lower = query.lower()

        # If user just wants a screenshot saved, confirm it
        if any(w in query_lower for w in ["save", "take", "capture"]) and not any(
            w in query_lower for w in ["look", "see", "what", "show", "describe", "analyze"]
        ):
            return f"Screenshot saved. What would you like me to do with it?"

        # Otherwise analyze
        return await _analyze_screenshot(image_path, query)
    except Exception as e:
        return f"I couldn't take a screenshot right now: {e}"
