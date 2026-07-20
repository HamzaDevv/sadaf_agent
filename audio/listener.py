"""
audio/listener.py — Full-duplex continuous audio listener with WebRTC VAD.
Replaces listen.py. Provides:
  - Continuous PyAudio frame reading (30ms chunks)
  - WebRTC VAD for speech/silence detection
  - Barge-in detection: sets interrupt_event if speech occurs during SPEAKING state
  - Automatic utterance segmentation → Groq Whisper transcription
"""
import asyncio
import io
import time
import threading
from typing import Optional

import pyaudio
import webrtcvad
import wave
import numpy as np
import noisereduce as nr
from groq import AsyncGroq

from config import (
    GROQ_API_KEY,
    STT_MODEL,
    VAD_AGGRESSIVENESS,
    VAD_FRAME_MS,
    VAD_SAMPLE_RATE,
    VAD_SILENCE_DURATION_MS,
    VAD_MIN_SPEECH_MS,
    VAD_POST_SPEECH_COOLDOWN_MS,
)

# ── Constants ────────────────────────────────────────────────────────────────
FRAME_SIZE = int(VAD_SAMPLE_RATE * VAD_FRAME_MS / 1000)   # samples per frame
BYTES_PER_FRAME = FRAME_SIZE * 2                            # 16-bit mono

groq_client = AsyncGroq(api_key=GROQ_API_KEY)
_vad = webrtcvad.Vad(VAD_AGGRESSIVENESS)


def _pcm_to_wav_bytes(pcm_bytes: bytes, sample_rate: int = VAD_SAMPLE_RATE) -> bytes:
    """Wrap raw PCM bytes in a WAV container."""
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)           # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
    return buf.getvalue()


def _denoise_pcm(pcm_bytes: bytes, sample_rate: int = VAD_SAMPLE_RATE) -> bytes:
    """Apply noisereduce to raw PCM bytes and return cleaned PCM."""
    arr = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
    try:
        cleaned = nr.reduce_noise(y=arr, sr=sample_rate, stationary=True)
    except Exception:
        cleaned = arr
    cleaned = np.clip(cleaned, -1.0, 1.0)
    return (cleaned * 32767).astype(np.int16).tobytes()


class ContinuousListener:
    """
    Full-duplex continuous microphone listener with VAD and barge-in support.
    
    Usage:
        listener = ContinuousListener(interrupt_event, speaking_flag)
        listener.start()
        utterance = await listener.utterance_queue.get()
        listener.stop()
    """

    def __init__(self, interrupt_event: asyncio.Event, is_speaking_ref: list):
        self.interrupt_event = interrupt_event
        self.is_speaking_ref = is_speaking_ref   # mutable list: [True/False]
        self.utterance_queue: asyncio.Queue[str] = asyncio.Queue()
        self._stop_event = threading.Event()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        # Time after which we accept mic input again (cooldown after AI speech)
        self._cooldown_until: float = 0.0

    def set_post_speech_cooldown(self):
        """Call this right after AI finishes speaking to suppress echo for a short window."""
        self._cooldown_until = time.time() + (VAD_POST_SPEECH_COOLDOWN_MS / 1000.0)

    def start(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)

    def _capture_loop(self):
        """Runs in background thread. Reads audio frames, runs VAD, segments utterances."""
        pa = pyaudio.PyAudio()
        stream = pa.open(
            rate=VAD_SAMPLE_RATE,
            channels=1,
            format=pyaudio.paInt16,
            input=True,
            frames_per_buffer=FRAME_SIZE,
        )

        # ── State variables ───────────────────────────────────────────────
        # How many consecutive speech frames needed to "trigger" recording
        # Use a low number (3 frames = 90ms) so it's responsive
        FRAMES_TO_TRIGGER = 3
        FRAMES_TO_STOP = VAD_SILENCE_DURATION_MS // VAD_FRAME_MS  # silence count

        triggered = False
        voiced_frames: list[bytes] = []
        speech_frame_count = 0     # consecutive speech frames before trigger
        silence_count = 0          # consecutive silence frames after trigger
        speech_start_time = 0.0
        pre_roll: list[bytes] = [] # last few frames before trigger (context)

        try:
            while not self._stop_event.is_set():
                frame = stream.read(FRAME_SIZE, exception_on_overflow=False)

                # ── VAD Classification ────────────────────────────────────
                try:
                    is_speech = _vad.is_speech(frame, VAD_SAMPLE_RATE)
                except Exception:
                    is_speech = False

                # ── Cooldown check (suppress echo after AI speaks) ────────
                if time.time() < self._cooldown_until:
                    # Drain frames silently during cooldown
                    triggered = False
                    voiced_frames = []
                    speech_frame_count = 0
                    silence_count = 0
                    pre_roll = []
                    continue

                # ── Barge-In Detection ────────────────────────────────────
                if is_speech and self.is_speaking_ref[0]:
                    if self._loop and self._loop.is_running():
                        self._loop.call_soon_threadsafe(self.interrupt_event.set)

                # ── NOT YET triggered: accumulate pre-roll + count speech ─
                if not triggered:
                    pre_roll.append(frame)
                    if len(pre_roll) > 10:   # keep ~300ms of pre-roll context
                        pre_roll.pop(0)

                    if is_speech:
                        speech_frame_count += 1
                    else:
                        speech_frame_count = max(0, speech_frame_count - 1)

                    if speech_frame_count >= FRAMES_TO_TRIGGER:
                        triggered = True
                        speech_start_time = time.time()
                        silence_count = 0
                        speech_frame_count = 0
                        # Include pre-roll for context
                        voiced_frames = list(pre_roll)
                        pre_roll = []

                # ── TRIGGERED: accumulate frames until silence ────────────
                else:
                    voiced_frames.append(frame)

                    if is_speech:
                        silence_count = 0
                    else:
                        silence_count += 1

                    # Long enough silence → end of utterance
                    if silence_count >= FRAMES_TO_STOP:
                        speech_duration_ms = (time.time() - speech_start_time) * 1000

                        if speech_duration_ms >= VAD_MIN_SPEECH_MS:
                            pcm = b"".join(voiced_frames)
                            if self._loop and self._loop.is_running():
                                asyncio.run_coroutine_threadsafe(
                                    self._transcribe_and_enqueue(pcm),
                                    self._loop
                                )
                        else:
                            pass  # Too short — discard (likely noise)

                        # Reset for next utterance
                        triggered = False
                        voiced_frames = []
                        silence_count = 0
                        speech_frame_count = 0
                        pre_roll = []

        finally:
            stream.stop_stream()
            stream.close()
            pa.terminate()

    async def _transcribe_and_enqueue(self, pcm_bytes: bytes):
        """Denoise PCM, send to Groq Whisper, put transcript in queue."""
        try:
            clean_pcm = await asyncio.to_thread(_denoise_pcm, pcm_bytes)
            wav_bytes = _pcm_to_wav_bytes(clean_pcm)

            transcription = await groq_client.audio.transcriptions.create(
                file=("audio.wav", wav_bytes),
                model=STT_MODEL,
                response_format="text",
            )
            text = str(transcription).strip()
            if text:
                print(f"\nYou: {text}")
                await self.utterance_queue.put(text)
        except Exception as e:
            print(f"[Listener] Transcription error: {e}")
