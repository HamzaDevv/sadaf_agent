"""
audio/listener_continuous.py — Sadaf V7 Continuous Listener
"""
import asyncio
import speech_recognition as sr
from audio.listen import transcribe_with_noise_reduction
from config import TIMEOUT, PHRASE_TIME_LIMIT, PAUSE_THRESHOLD, ENERGY_THRESHOLD

class ContinuousListener:
    def __init__(self):
        self.recognizer = sr.Recognizer()
        self.recognizer.pause_threshold = PAUSE_THRESHOLD
        self.recognizer.energy_threshold = ENERGY_THRESHOLD
        self.recognizer.dynamic_energy_threshold = True
        self.is_listening = False

        self.microphone = sr.Microphone()
        print("[ContinuousListener] Adjusting for ambient noise...")
        with self.microphone as source:
            self.recognizer.adjust_for_ambient_noise(source, 1.0)

    async def listen(self) -> str:
        """Continuously listens and returns transcribed text when speech is detected."""
        self.is_listening = True
        while self.is_listening:
            try:
                with self.microphone as source:
                    audio = await asyncio.to_thread(
                        self.recognizer.listen, source, TIMEOUT, PHRASE_TIME_LIMIT
                    )

                if not self.is_listening:
                    break

                text = await transcribe_with_noise_reduction(audio)
                if text:
                    return text

            except sr.WaitTimeoutError:
                continue
            except Exception as e:
                print(f"[ContinuousListener] Error: {e}")
                await asyncio.sleep(0.1)

        return ""

    def stop(self):
        """Stops the listening loop."""
        self.is_listening = False
