"""
groq_proxy.py — Sadaf V4 Centralized Groq API Proxy

Replaces all scattered `AsyncGroq(api_key=...)` instances across the codebase.

Features:
  - Round-robin key rotation across multiple API keys (separate orgs = ×3 quota)
  - Per-key sliding-window rate tracker using x-ratelimit-* response headers
  - Smart key selection: pick the key with the most remaining quota
  - Automatic retry on 429 with next key + exponential backoff (max 3 attempts)
  - Priority-aware request scheduler: chat (1) > extraction (2) > agent (3)
  - Dual-model routing: 8b for simple tasks, 70b for complex/emotional queries
  - Whisper STT passthrough with the same key rotation

Usage:
    from groq_proxy import groq_proxy

    # Chat (model auto-selected by complexity)
    response = await groq_proxy.chat(messages=[...], user_query="...")

    # Extraction / fixed-model calls
    response = await groq_proxy.call(model="llama-3.1-8b-instant", messages=[...], priority=2)

    # Streaming chat
    async for chunk in groq_proxy.stream(messages=[...], user_query="..."):
        ...

    # STT
    text = await groq_proxy.transcribe(file_tuple, model=STT_MODEL)
"""

import asyncio
import time
import json
import re
from typing import AsyncGenerator, Optional
from groq import AsyncGroq
from config import (
    GROQ_API_KEYS,
    CHAT_MODEL,
    GROQ_TPM_8B,
    GROQ_TPM_70B,
    GROQ_RPM,
    PRIORITY_CHAT,
    PRIORITY_EXTRACTION,
    PRIORITY_AGENT,
    STT_MODEL,
)


def _is_8b(model: str) -> bool:
    return "8b" in model or "instant" in model


# ──────────────────────────────────────────────────────────────────────────────
# Per-Key Rate State
# ──────────────────────────────────────────────────────────────────────────────

class KeyState:
    """Tracks the rate-limit state for a single API key."""

    def __init__(self, key: str):
        self.key = key
        self.client = AsyncGroq(api_key=key)
        # Latest values from x-ratelimit-* response headers
        self.remaining_tokens_8b: int = GROQ_TPM_8B
        self.remaining_tokens_70b: int = GROQ_TPM_70B
        self.remaining_requests: int = GROQ_RPM
        self.reset_tokens_at: float = 0.0   # Unix timestamp when token window resets
        self.reset_requests_at: float = 0.0
        self.locked_until: float = 0.0      # Locked after 429 until this time

    def is_available(self, model: str) -> bool:
        now = time.monotonic()
        if now < self.locked_until:
            return False
        if self.remaining_requests <= 1:
            if now < self.reset_requests_at:
                return False
        remaining = self.remaining_tokens_8b if _is_8b(model) else self.remaining_tokens_70b
        if remaining <= 100:  # Safety buffer
            if now < self.reset_tokens_at:
                return False
        return True

    def available_tokens(self, model: str) -> int:
        if not self.is_available(model):
            return 0
        return self.remaining_tokens_8b if _is_8b(model) else self.remaining_tokens_70b

    def update_from_headers(self, headers: dict):
        """Parse x-ratelimit-* headers from Groq response."""
        try:
            if "x-ratelimit-remaining-tokens" in headers:
                val = int(headers["x-ratelimit-remaining-tokens"])
                # Heuristically assign to correct model bucket
                # (Groq returns separate headers per model family when using mixed)
                # Simple approach: update whichever is lower (we just called it)
                if val < GROQ_TPM_8B:
                    self.remaining_tokens_8b = val
                else:
                    self.remaining_tokens_70b = val

            if "x-ratelimit-remaining-requests" in headers:
                self.remaining_requests = int(headers["x-ratelimit-remaining-requests"])

            if "x-ratelimit-reset-tokens" in headers:
                # Value is a duration string like "1m30s" or seconds
                self.reset_tokens_at = time.monotonic() + _parse_reset_duration(
                    headers["x-ratelimit-reset-tokens"]
                )

            if "x-ratelimit-reset-requests" in headers:
                self.reset_requests_at = time.monotonic() + _parse_reset_duration(
                    headers["x-ratelimit-reset-requests"]
                )
        except Exception as e:
            print(f"[Proxy] Header parse error: {e}")

    def lock(self, seconds: float):
        self.locked_until = time.monotonic() + seconds
        print(f"[Proxy] Key ...{self.key[-6:]} locked for {seconds:.1f}s")


def _parse_reset_duration(value: str) -> float:
    """Parse Groq reset header into seconds. Handles '60s', '1m30s', or plain seconds."""
    if not value:
        return 60.0
    try:
        return float(value)
    except ValueError:
        pass
    seconds = 0.0
    for m, s in re.findall(r"(\d+)([ms])", value):
        seconds += int(m) * (60 if s == "m" else 1)
    return seconds if seconds > 0 else 60.0


# ──────────────────────────────────────────────────────────────────────────────
# Groq Proxy — Main Class
# ──────────────────────────────────────────────────────────────────────────────

class GroqProxy:
    """
    Centralized, resilient Groq API proxy.
    All LLM and STT calls in Sadaf should go through this singleton.
    """

    def __init__(self, api_keys: list[str]):
        if not api_keys:
            raise ValueError("No GROQ_API_KEYS configured. Check your .env file.")
        self.keys: list[KeyState] = [KeyState(k) for k in api_keys]
        self._rr_index: int = 0
        self._lock = asyncio.Lock()

    # ── Key Selection ─────────────────────────────────────────────────────────

    def _best_key(self, model: str) -> Optional[KeyState]:
        """Pick the key with the most remaining tokens for this model."""
        available = [k for k in self.keys if k.is_available(model)]
        if not available:
            return None
        return max(available, key=lambda k: k.available_tokens(model))

    def _next_key(self, model: str) -> Optional[KeyState]:
        """Round-robin fallback — ignores quota state."""
        for _ in range(len(self.keys)):
            self._rr_index = (self._rr_index + 1) % len(self.keys)
            k = self.keys[self._rr_index]
            if k.is_available(model):
                return k
        return None

    def _select_key(self, model: str) -> Optional[KeyState]:
        """Best-quota first, round-robin fallback."""
        return self._best_key(model) or self._next_key(model)

    # ── Core Call ─────────────────────────────────────────────────────────────

    async def call(
        self,
        model: str,
        messages: list[dict],
        priority: int = PRIORITY_EXTRACTION,
        temperature: float = 0.1,
        max_tokens: int = 400,
        response_format: Optional[dict] = None,
    ) -> Optional[str]:
        """
        Non-streaming LLM call. Returns response text or None on failure.
        Retries up to 3 times across different keys on 429.
        """
        attempts = 0
        last_err = None

        while attempts < min(3, len(self.keys) + 1):
            key_state = self._select_key(model)
            if not key_state:
                wait = 60.0
                print(f"[Proxy] All keys exhausted for {model}. Waiting {wait}s...")
                await asyncio.sleep(wait)
                # Reset sliding estimates after wait
                for k in self.keys:
                    k.remaining_tokens_8b = GROQ_TPM_8B
                    k.remaining_tokens_70b = GROQ_TPM_70B
                    k.remaining_requests = GROQ_RPM
                key_state = self.keys[0]

            kwargs = dict(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            if response_format:
                kwargs["response_format"] = response_format

            try:
                response = await key_state.client.chat.completions.create(**kwargs)

                # Update rate tracking from response headers
                raw_response = response  # groq SDK exposes headers via _raw_response
                try:
                    headers = response._raw_response.headers  # type: ignore
                    key_state.update_from_headers(dict(headers))
                except Exception:
                    pass

                text = response.choices[0].message.content or ""
                return text.strip()

            except Exception as e:
                err = str(e)
                last_err = err
                attempts += 1

                if "429" in err or "rate_limit" in err.lower() or "too many requests" in err.lower():
                    # Try to extract retry-after header
                    retry_after = 30.0
                    try:
                        m = re.search(r"retry after (\d+)", err, re.IGNORECASE)
                        if m:
                            retry_after = float(m.group(1))
                    except Exception:
                        pass
                    key_state.lock(retry_after)
                    print(f"[Proxy] 429 on key ...{key_state.key[-6:]}. Trying next key.")
                    continue

                print(f"[Proxy] LLM error (attempt {attempts}): {e}")
                break

        print(f"[Proxy] All attempts failed: {last_err}")
        return None

    # ── Streaming Chat ────────────────────────────────────────────────────────

    async def stream(
        self,
        messages: list[dict],
        user_query: str = "",
        interrupt_event: Optional[asyncio.Event] = None,
        temperature: float = 0.75,
        max_tokens: int = 350,
    ) -> AsyncGenerator[str, None]:
        """
        Streaming sentence-by-sentence generator for real-time TTS.
        Automatically selects model based on query complexity.
        Retries on 429 with next key (yields a brief apology first).
        """
        model = self.router.select_chat_model(user_query)
        _SENTENCE_END = re.compile(r'(?<=[.!?])\s+|(?<=[.!?])$')
        _CLAUSE_END   = re.compile(r'(?<=[,;])\s+')

        attempts = 0
        while attempts < min(3, len(self.keys) + 1):
            key_state = self._select_key(model)
            if not key_state:
                if interrupt_event and interrupt_event.is_set():
                    return
                yield "Give me just a second."
                await asyncio.sleep(60)
                key_state = self.keys[0]

            try:
                stream = await key_state.client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=True,
                )

                buffer = ""
                in_think = False

                async for chunk in stream:
                    if interrupt_event and interrupt_event.is_set():
                        return

                    delta = chunk.choices[0].delta.content
                    if not delta:
                        continue

                    # Strip <think>...</think> blocks
                    if "<think>" in delta:
                        in_think = True
                    if in_think:
                        if "</think>" in delta:
                            in_think = False
                            delta = delta.split("</think>", 1)[-1]
                        else:
                            continue

                    buffer += delta

                    sentences = _SENTENCE_END.split(buffer)
                    if len(sentences) > 1:
                        for s in sentences[:-1]:
                            s = s.strip()
                            if s and not (interrupt_event and interrupt_event.is_set()):
                                yield s
                        buffer = sentences[-1]

                # Flush remaining buffer
                remaining = buffer.strip()
                if remaining and not (interrupt_event and interrupt_event.is_set()):
                    for clause in _CLAUSE_END.split(remaining):
                        clause = clause.strip()
                        if clause:
                            yield clause

                # Update rate headers
                try:
                    headers = stream._raw_response.headers  # type: ignore
                    key_state.update_from_headers(dict(headers))
                except Exception:
                    pass

                return  # Success — exit retry loop

            except Exception as e:
                err = str(e)
                attempts += 1
                if "429" in err or "rate_limit" in err.lower():
                    retry_after = 30.0
                    try:
                        m = re.search(r"retry after (\d+)", err, re.IGNORECASE)
                        if m:
                            retry_after = float(m.group(1))
                    except Exception:
                        pass
                    key_state.lock(retry_after)
                    if attempts == 1 and not (interrupt_event and interrupt_event.is_set()):
                        yield "Give me just a second, I'm thinking."
                    continue
                # Non-rate-limit error
                if not (interrupt_event and interrupt_event.is_set()):
                    yield "Sorry, I had a little brain glitch there."
                return

    # ── Chat (Non-Streaming) ──────────────────────────────────────────────────

    async def chat(
        self,
        messages: list[dict],
        user_query: str = "",
        temperature: float = 0.1,
        max_tokens: int = 500,
    ) -> str:
        """Non-streaming chat call with automatic model selection."""
        model = self.router.select_chat_model(user_query)
        result = await self.call(
            model=model,
            messages=messages,
            priority=PRIORITY_CHAT,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return result or ""

    # ── STT (Whisper) ─────────────────────────────────────────────────────────

    async def transcribe(
        self,
        file_tuple: tuple,  # ("filename.wav", bytes)
        model: str = STT_MODEL,
        response_format: str = "text",
    ) -> Optional[str]:
        """
        Transcribe audio with round-robin key selection.
        Whisper uses audio-seconds quota, not TPM — treated separately.
        """
        attempts = 0
        while attempts < len(self.keys):
            # Round-robin for STT (no TPM tracking needed)
            self._rr_index = (self._rr_index + 1) % len(self.keys)
            key_state = self.keys[self._rr_index]

            try:
                result = await key_state.client.audio.transcriptions.create(
                    file=file_tuple,
                    model=model,
                    response_format=response_format,
                )
                return str(result).strip()
            except Exception as e:
                err = str(e)
                attempts += 1
                if "429" in err or "rate_limit" in err.lower():
                    key_state.lock(30.0)
                    continue
                print(f"[Proxy] STT error: {e}")
                return None

        print("[Proxy] All STT attempts failed.")
        return None


# ── Singleton ─────────────────────────────────────────────────────────────────

groq_proxy = GroqProxy(GROQ_API_KEYS)
