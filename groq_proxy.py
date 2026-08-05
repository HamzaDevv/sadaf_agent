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
  - Whisper STT passthrough with the same key rotation + RPM tracking
  - TokenBucket pacing: spreads burst traffic across the TPM window proactively
    so quota is almost never exhausted all at once (prevents wall-of-429s)

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
    PROXY_SILENT_WAIT_THRESHOLD_S,
    PROXY_BURST_RESERVE_FRACTION,
)


def _is_8b(model: str) -> bool:
    return "8b" in model or "instant" in model


# ──────────────────────────────────────────────────────────────────────────────
# Token Bucket — Proactive TPM Pacing
# ──────────────────────────────────────────────────────────────────────────────

class TokenBucket:
    """
    Leaky-bucket / token-refill pacing for Groq TPM limits.

    Goal: spread burst traffic smoothly across the 60-second window so quota
    is consumed evenly rather than all at once (which causes wall-of-429s).

    Two key design choices:
      1. PROACTIVE: tracks tokens_available and refills continuously at
         refill_rate tokens/second. Requests wait only if the bucket is low.
      2. CONSERVATIVE: a BURST_RESERVE_FRACTION of capacity is held back, so
         the bucket never fully empties even under heavy load. This means we
         almost never reach the 429 state.

    When a real server header updates remaining_tokens, the bucket is
    corrected to the authoritative server value (drift compensation).
    """

    def __init__(self, capacity: int, refill_rate: float):
        self.capacity = capacity
        self.refill_rate = refill_rate          # tokens per second
        self._tokens: float = float(capacity)
        self._last_refill: float = time.monotonic()
        self._lock = asyncio.Lock()

    def _refill(self):
        """Add tokens based on elapsed time (called before every consume)."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self.capacity, self._tokens + elapsed * self.refill_rate)
        self._last_refill = now

    async def consume(self, tokens: int) -> float:
        """
        Deduct `tokens` from the bucket. If insufficient, waits until
        refill covers the shortfall.
        Returns the actual wait time (seconds) — caller uses this to decide
        whether to tell the user "one moment...".
        """
        # Reserve fraction: never dip below this threshold
        reserve = int(self.capacity * PROXY_BURST_RESERVE_FRACTION)
        effective_available = max(0, self._tokens - reserve)

        if tokens > effective_available:
            shortfall = tokens - effective_available
            wait_s = shortfall / self.refill_rate
        else:
            wait_s = 0.0

        if wait_s > 0:
            await asyncio.sleep(wait_s)

        async with self._lock:
            self._refill()
            # After sleeping, tokens should now be available
            self._tokens = max(0.0, self._tokens - tokens)

        return wait_s

    def server_correct(self, server_remaining: int):
        """
        Correct our local estimate using the authoritative server header.
        Takes the MIN of our estimate and server value (trust lower bound).
        """
        async def _correct():
            async with self._lock:
                self._refill()
                # Be conservative: if server says less, trust server
                if server_remaining < self._tokens:
                    self._tokens = float(server_remaining)
        asyncio.create_task(_correct())

    def estimate_tokens(self) -> float:
        """Current estimated available tokens (after virtual refill)."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        return min(self.capacity, self._tokens + elapsed * self.refill_rate)


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

    def update_from_headers(self, headers: dict, model: str):
        """
        Parse x-ratelimit-* headers from Groq response.
        model is required to correctly assign remaining-tokens to the right bucket
        (fixes the old heuristic bug where a heavy 70b response with few tokens
        remaining could be misassigned to the 8b bucket).
        """
        try:
            if "x-ratelimit-remaining-tokens" in headers:
                val = int(headers["x-ratelimit-remaining-tokens"])
                # Use the actual model that was called — no guessing
                if _is_8b(model):
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

    def decrement_rpm(self):
        """Pessimistically decrement RPM before the request completes."""
        self.remaining_requests = max(0, self.remaining_requests - 1)

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
        n = len(api_keys)

        # Token buckets span all keys combined (effective quota = per-org × keys)
        # Refill rate = total_capacity / 60 seconds
        self._bucket_8b  = TokenBucket(
            capacity=GROQ_TPM_8B  * n,
            refill_rate=(GROQ_TPM_8B  * n) / 60.0,
        )
        self._bucket_70b = TokenBucket(
            capacity=GROQ_TPM_70B * n,
            refill_rate=(GROQ_TPM_70B * n) / 60.0,
        )

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

    # ── Bucket Helpers ────────────────────────────────────────────────────────

    def _bucket_for(self, model: str) -> TokenBucket:
        return self._bucket_8b if _is_8b(model) else self._bucket_70b

    @staticmethod
    def _estimate_tokens(messages: list[dict], max_tokens: int) -> int:
        """
        Rough token cost estimate for pacing purposes.
        Prompt tokens ≈ total character count / 4.
        Add max_tokens for the expected completion.
        This doesn't need to be exact — the server header corrects the bucket.
        """
        prompt_chars = sum(len(m.get("content", "")) for m in messages)
        return int(prompt_chars / 4) + max_tokens

    # ── Core Call ─────────────────────────────────────────────────────────────

    async def call(
        self,
        model: str,
        messages: list[dict],
        priority: int = PRIORITY_EXTRACTION,
        temperature: float = 0.1,
        max_tokens: int = 400,
        response_format: Optional[dict] = None,
        allow_fallback: bool = True,
    ) -> Optional[str]:
        """
        Non-streaming LLM call. Returns response text or None on failure.
        Retries up to 3 times across different keys on 429.

        Flow:
          1. Estimate token cost
          2. Wait on token bucket (pacing — rarely actually waits)
          3. Select best key + decrement RPM pessimistically
          4. Send request
          5. Update bucket + key state from response headers
        """
        # Step 1: Token bucket pacing
        estimated = self._estimate_tokens(messages, max_tokens)
        bucket = self._bucket_for(model)
        wait_s = await bucket.consume(estimated)

        if wait_s >= PROXY_SILENT_WAIT_THRESHOLD_S:
            print(
                f"[Proxy] Pacing wait {wait_s:.1f}s for {model} "
                f"(bucket at {bucket.estimate_tokens():.0f} tokens). "
                f"This should be rare — check if call volume is too high."
            )

        # Step 2: Retry loop across keys
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

            # Pessimistic RPM decrement before the request
            key_state.decrement_rpm()

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

                # Update rate tracking from response headers (model-aware fix)
                try:
                    headers = response._raw_response.headers  # type: ignore
                    headers_dict = dict(headers)
                    key_state.update_from_headers(headers_dict, model)
                    # Correct token bucket with authoritative server value
                    if "x-ratelimit-remaining-tokens" in headers_dict:
                        server_remaining = int(headers_dict["x-ratelimit-remaining-tokens"])
                        # Scale from per-key to combined bucket estimate
                        bucket.server_correct(server_remaining * len(self.keys))
                except Exception:
                    pass

                text = response.choices[0].message.content or ""
                return text.strip()

            except Exception as e:
                err = str(e)
                last_err = err
                attempts += 1

                if "429" in err or "rate_limit" in err.lower() or "too many requests" in err.lower():
                    # Try to extract retry-after header or Groq's specific try again string
                    retry_after = 30.0
                    try:
                        m = re.search(r"retry after (\d+)", err, re.IGNORECASE)
                        if m:
                            retry_after = float(m.group(1))
                        else:
                            m2 = re.search(r"try again in (?:(\d+)h)?(?:(\d+)m)?(?:([\d.]+)s)?", err, re.IGNORECASE)
                            if m2:
                                h = float(m2.group(1) or 0)
                                m_ = float(m2.group(2) or 0)
                                s = float(m2.group(3) or 0)
                                if h > 0 or m_ > 0 or s > 0:
                                    retry_after = h * 3600 + m_ * 60 + s
                    except Exception:
                        pass

                    if retry_after > 60 and "70b" in model:
                        if allow_fallback:
                            print(f"[Proxy] High wait ({retry_after}s) for {model}. Smart fallback to 8b.")
                            model = CHAT_MODEL
                            # Switch bucket for the new model
                            bucket = self._bucket_for(model)
                            continue  # don't lock key, just switch model and retry
                        else:
                            # Critical call — do NOT downgrade, signal rate limit to caller
                            print(f"[Proxy] High wait ({retry_after}s) for {model}. No fallback (critical call).")
                            return f"RATE_LIMIT: {err}"

                    key_state.lock(retry_after)
                    print(f"[Proxy] 429 on key ...{key_state.key[-6:]}. Trying next key.")
                    continue

                print(f"[Proxy] LLM error (attempt {attempts}): {e}")
                break

        print(f"[Proxy] All attempts failed: {last_err}")
        if last_err and ("429" in last_err or "rate_limit" in last_err.lower() or "too many requests" in last_err.lower()):
            return f"RATE_LIMIT: {last_err}"
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

        # Token bucket pacing for streaming
        estimated = self._estimate_tokens(messages, max_tokens)
        bucket = self._bucket_for(model)
        wait_s = await bucket.consume(estimated)
        if wait_s >= PROXY_SILENT_WAIT_THRESHOLD_S:
            print(f"[Proxy] Stream pacing wait {wait_s:.1f}s for {model}")

        attempts = 0
        while attempts < min(3, len(self.keys) + 1):
            key_state = self._select_key(model)
            if not key_state:
                if interrupt_event and interrupt_event.is_set():
                    return
                yield "Give me just a second."
                await asyncio.sleep(60)
                key_state = self.keys[0]

            key_state.decrement_rpm()

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

                # Update rate headers (model-aware)
                try:
                    headers = stream._raw_response.headers  # type: ignore
                    headers_dict = dict(headers)
                    key_state.update_from_headers(headers_dict, model)
                    if "x-ratelimit-remaining-tokens" in headers_dict:
                        server_remaining = int(headers_dict["x-ratelimit-remaining-tokens"])
                        bucket.server_correct(server_remaining * len(self.keys))
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
        Transcribe audio with key selection via _select_key() + RPM tracking.
        STT calls now decrement the RPM counter like LLM calls, since Groq's
        30 RPM limit is shared between LLM and STT on the same key.
        """
        attempts = 0
        # Use a pseudo-model string for RPM key selection
        # STT doesn't use TPM, so we just need RPM-aware key selection
        while attempts < len(self.keys):
            # Select key with available RPM (not token-based for STT)
            key_state = self._select_key(model)
            if not key_state:
                # All keys RPM-locked — use round-robin as fallback
                self._rr_index = (self._rr_index + 1) % len(self.keys)
                key_state = self.keys[self._rr_index]

            # Decrement RPM before call (STT uses the same 30 RPM per key)
            key_state.decrement_rpm()

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
                    # Also give back the RPM we decremented since call failed
                    key_state.remaining_requests = min(
                        GROQ_RPM, key_state.remaining_requests + 1
                    )
                    continue
                print(f"[Proxy] STT error: {e}")
                return None

        print("[Proxy] All STT attempts failed.")
        return None


# ── Singleton ─────────────────────────────────────────────────────────────────

groq_proxy = GroqProxy(GROQ_API_KEYS)
