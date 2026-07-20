import os
import asyncio
from config import VOICE, MAX_RESPONSE_WORDS


import subprocess

async def speak_async_system(text: str):
    """Fast, short macOS TTS using 'say' command."""
    # Pre-truncate words for speed
    words = text.split()
    shortened_text = " ".join(words[:MAX_RESPONSE_WORDS])
    if len(words) > MAX_RESPONSE_WORDS:
        shortened_text += "..."

    print(f"AI: {shortened_text}")

    try:
        # Run TTS without blocking main event loop and without shell injection risk
        await asyncio.to_thread(
            subprocess.run,
            ["say", "-v", VOICE, shortened_text],
            check=False
        )
    except Exception as e:
        print(f"TTS error: {e}")
