"""
audio/speaker.py — Interruptible sentence-by-sentence TTS using macOS 'say'.
Replaces speak.py. Key features:
  - Uses subprocess.Popen (non-blocking) so we can kill mid-sentence on barge-in
  - Natural randomized pauses between sentences (80-200ms)
  - Randomized speech rate for human-like variation
  - Exposes is_speaking property and stop() method
"""
import asyncio
import subprocess
import random
from config import VOICE


def _random_rate() -> int:
    """Randomize speech rate between 175-200 wpm for natural variation."""
    return random.randint(175, 200)


def _random_pause() -> float:
    """Randomize inter-sentence pause 80-200ms."""
    return random.uniform(0.08, 0.20)


class InterruptibleSpeaker:
    """
    Sentence-by-sentence TTS speaker that can be immediately interrupted.
    
    Usage:
        speaker = InterruptibleSpeaker(interrupt_event, is_speaking_ref)
        await speaker.speak("Hello there.")
        speaker.stop()   # kills immediately
    """

    def __init__(self, interrupt_event: asyncio.Event, is_speaking_ref: list, listener=None):
        self.interrupt_event = interrupt_event
        self.is_speaking_ref = is_speaking_ref  # mutable [bool]
        self._process: subprocess.Popen | None = None
        self._listener = listener  # set after listener is created

    def stop(self):
        """Kill any active TTS process immediately."""
        if self._process and self._process.poll() is None:
            self._process.kill()
            self._process = None
        self.is_speaking_ref[0] = False

    async def speak_sentence(self, text: str) -> bool:
        """
        Speak a single sentence. Returns True if completed, False if interrupted.
        """
        if not text.strip():
            return True

        # Clear the interrupt event before speaking
        self.interrupt_event.clear()
        self.is_speaking_ref[0] = True

        rate = _random_rate()
        print(f"Sadaf: {text}")

        # Launch say as a non-blocking subprocess
        self._process = await asyncio.to_thread(
            subprocess.Popen,
            ["say", "-v", VOICE, "-r", str(rate), text],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # Poll until done or interrupted
        while True:
            # Check if process finished
            retcode = await asyncio.to_thread(self._process.poll)
            if retcode is not None:
                break

            # Check if interrupted
            if self.interrupt_event.is_set():
                self.stop()
                return False  # Interrupted

            await asyncio.sleep(0.03)  # 30ms poll interval

        self.is_speaking_ref[0] = False
        # Trigger cooldown to suppress echo feedback
        if self._listener:
            self._listener.set_post_speech_cooldown()
        return True  # Completed normally

    async def speak(self, text: str):
        """
        Speak a full text (already chunked by caller). Handles inter-sentence pauses.
        Returns when done or interrupted.
        """
        from utils import chunk_at_boundaries
        chunks = chunk_at_boundaries(text)

        for chunk in chunks:
            if self.interrupt_event.is_set():
                self.stop()
                return

            completed = await self.speak_sentence(chunk)
            if not completed:
                return  # Barge-in detected — stop speaking

            # Natural inter-sentence pause
            pause = _random_pause()
            await asyncio.sleep(pause)
