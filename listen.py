"""
listen.py — Sadaf V4 Audio Input + Groq Whisper STT

V4 changes:
  - Uses groq_proxy.transcribe() for STT (key rotation, retry on 429)
  - Otherwise identical VAD + noise reduction pipeline
"""
import asyncio
import io
import time
from typing import Optional
import numpy as np
import speech_recognition as sr
from pydub import AudioSegment
import noisereduce as nr

from groq_proxy import groq_proxy
from config import (
    PAUSE_THRESHOLD,
    ENERGY_THRESHOLD,
    TIMEOUT,
    PHRASE_TIME_LIMIT,
    STT_MODEL,
)

recognizer = sr.Recognizer()
recognizer.pause_threshold = PAUSE_THRESHOLD
recognizer.energy_threshold = ENERGY_THRESHOLD
recognizer.dynamic_energy_threshold = True

_NOISE_PROFILE: Optional[np.ndarray] = None


def _audiosegment_from_wav_bytes(wav_bytes: bytes) -> AudioSegment:
    bio = io.BytesIO(wav_bytes)
    bio.seek(0)
    return AudioSegment.from_file(bio, format="wav")


def _normalize_samples(arr: np.ndarray, sample_width: int) -> np.ndarray:
    if sample_width == 2:
        return arr.astype(np.float32) / 32768.0
    if sample_width == 4:
        return arr.astype(np.float32) / 2147483648.0
    return arr.astype(np.float32) / 32768.0


def _float_to_pcm_bytes(arr: np.ndarray, sample_width: int) -> bytes:
    arr_clipped = np.clip(arr, -1.0, 1.0)
    if sample_width == 2:
        pcm = (arr_clipped * 32767).astype(np.int16)
    elif sample_width == 4:
        pcm = (arr_clipped * 2147483647).astype(np.int32)
    else:
        pcm = (arr_clipped * 32767).astype(np.int16)
    return pcm.tobytes()


async def listen_once(timeout: int = TIMEOUT, phrase_time_limit: int = PHRASE_TIME_LIMIT) -> Optional[sr.AudioData]:
    try:
        with sr.Microphone() as source:
            await asyncio.to_thread(recognizer.adjust_for_ambient_noise, source, 0.8)
            audio = await asyncio.to_thread(
                recognizer.listen, source, timeout, phrase_time_limit
            )
            return audio
    except sr.WaitTimeoutError:
        return None
    except Exception as exc:
        print(f"[listen_once] error: {exc}")
        await asyncio.sleep(0.05)
        return None


async def transcribe_with_noise_reduction(audio: sr.AudioData) -> Optional[str]:
    global _NOISE_PROFILE

    if audio is None:
        return None

    try:
        wav_bytes = audio.get_wav_data()
        sound = await asyncio.to_thread(_audiosegment_from_wav_bytes, wav_bytes)

        arr = np.array(sound.get_array_of_samples())
        sample_width = sound.sample_width
        channels = sound.channels
        frame_rate = sound.frame_rate

        if channels > 1:
            arr = arr.reshape((-1, channels)).mean(axis=1)

        norm = _normalize_samples(arr, sample_width)

        if _NOISE_PROFILE is None:
            try:
                _NOISE_PROFILE = nr.reduce_noise(y=norm, sr=frame_rate, stationary=True)
            except Exception:
                _NOISE_PROFILE = None

        try:
            reduced = nr.reduce_noise(y=norm, sr=frame_rate, stationary=True)
        except Exception:
            reduced = norm

        pcm_bytes = _float_to_pcm_bytes(reduced, sample_width)
        clean_segment = AudioSegment(
            data=pcm_bytes,
            sample_width=sample_width,
            frame_rate=frame_rate,
            channels=1,
        )

        bio = io.BytesIO()
        clean_segment.export(bio, format="wav")
        audio_file_bytes = bio.getvalue()

        # Use groq_proxy for STT (round-robin key rotation)
        text = await groq_proxy.transcribe(
            file_tuple=("audio.wav", audio_file_bytes),
            model=STT_MODEL,
            response_format="text",
        )

        if not text:
            return None

        # Filter out common Whisper hallucinations for silence
        lower_text = text.strip().lower()
        hallucinations = [
            "no input string", "thank you for watching", "thanks for watching",
            "subtitles by", "amara.org", "you", "subscribe", "please subscribe",
            "thank you", "bye", "bye bye", "it's"
        ]
        import string
        clean_text = lower_text.translate(str.maketrans('', '', string.punctuation)).strip()

        if not clean_text or any(h == clean_text for h in hallucinations):
            return None

        timestamp = time.strftime("%H:%M:%S", time.localtime())
        print(f"You: {text}")
        return f"{timestamp} - {text}"

    except Exception as exc:
        print(f"[transcribe_with_noise_reduction] error: {exc}")

    return None
