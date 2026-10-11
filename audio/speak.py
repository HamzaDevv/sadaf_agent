"""
speak.py — Sadaf macOS TTS Synthesizer
"""
import os
import asyncio
import subprocess
import tempfile
from config import VOICE, MAX_RESPONSE_WORDS


async def speak_async_system(text: str):
    """Fast, short macOS TTS using 'say' command."""
    # Pre-truncate words for speed
    words = text.split()
    shortened_text = " ".join(words[:MAX_RESPONSE_WORDS])
    if len(words) > MAX_RESPONSE_WORDS:
        shortened_text += "..."

    if os.getenv("SADAF_VOICE_PROVIDER", "macos").lower() == "openrouter":
        # Paid TTS is explicit opt-in; local macOS speech remains the $0 default.
        try:
            from config import OPENROUTER_API_KEY
            from sadaf.tts import OpenRouterTTSSynthesizer
            audio = await OpenRouterTTSSynthesizer(OPENROUTER_API_KEY).synthesize(shortened_text)
            def play_mp3():
                path = None
                try:
                    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as file:
                        path = file.name
                        file.write(audio)
                    subprocess.run(["afplay", path], check=False)
                finally:
                    if path and os.path.exists(path): os.unlink(path)
            await asyncio.to_thread(play_mp3)
            return
        except Exception:
            print("OpenRouter TTS failed; using local macOS speech.")

    try:
        # Run TTS without blocking main event loop and without shell injection risk
        await asyncio.to_thread(
            subprocess.run,
            ["say", "-v", VOICE, shortened_text],
            check=False
        )
    except Exception as e:
        print(f"TTS error: {e}")
