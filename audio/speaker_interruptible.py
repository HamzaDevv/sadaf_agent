"""
audio/speaker_interruptible.py — Sadaf V7 Interruptible TTS
"""
import asyncio
import subprocess
import re
from typing import Optional
from config import VOICE

class InterruptibleSpeaker:
    def __init__(self):
        self.current_process: Optional[subprocess.Popen] = None

    def stop(self):
        """Terminates any ongoing TTS playback immediately."""
        if self.current_process:
            try:
                self.current_process.terminate()
            except Exception:
                pass
            self.current_process = None

    async def speak(self, text: str):
        """
        Speaks text chunk-by-chunk. If stop() is called, the loop breaks early.
        """
        self.stop()

        # Simple sentence chunking
        sentences = re.split(r'(?<=[.!?]) +', text.replace('\n', ' '))
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            self.current_process = subprocess.Popen(
                ["say", "-v", VOICE, sentence],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

            # Wait for process to finish or be interrupted
            while self.current_process and self.current_process.poll() is None:
                await asyncio.sleep(0.1)

            # If current_process is None, we were interrupted
            if not self.current_process:
                break
