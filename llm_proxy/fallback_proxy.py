"""
fallback_proxy.py — Gemini-first with automatic Groq fallback.

When all Gemini keys are exhausted (daily or per-minute quota), every
call/stream/chat transparently falls through to Groq so Sadaf keeps
working without any user-visible interruption.
"""
import asyncio
from typing import AsyncGenerator, Optional, List, Dict, Any

from llm_proxy.base import BaseLLMProxy
from llm_proxy.gemini_impl import GeminiProxyImpl
from llm_proxy.groq_impl import GroqProxyImpl
from config import CHAT_MODEL

# Map Gemini model names → nearest Groq equivalents
_GEMINI_TO_GROQ: dict[str, str] = {
    "gemini-2.0-flash":       "llama-3.3-70b-versatile",
    "gemini-2.0-flash-lite":  "llama-3.1-8b-instant",
    "gemini-1.5-flash":       "llama-3.3-70b-versatile",
    "gemini-1.5-flash-8b":    "llama-3.1-8b-instant",
    "gemini-1.5-pro":         "llama-3.3-70b-versatile",
}

def _groq_model(gemini_model: str) -> str:
    """Return the Groq equivalent for a Gemini model name."""
    return _GEMINI_TO_GROQ.get(gemini_model, "llama-3.1-8b-instant")

def _is_rate_limited(result: Optional[str]) -> bool:
    return result is None or (isinstance(result, str) and result.startswith("RATE_LIMIT:"))


class FallbackProxy(BaseLLMProxy):
    """
    Transparent Gemini → Groq failover proxy.

    Primary: GeminiProxyImpl (4 keys, free tier)
    Fallback: GroqProxyImpl  (3 keys, free tier)

    Fallback triggers when:
    - Gemini returns None (all attempts failed)
    - Gemini returns a RATE_LIMIT: ... string
    """

    def __init__(self):
        self._gemini = GeminiProxyImpl()
        self._groq   = GroqProxyImpl()
        print(f"[FallbackProxy] Gemini keys: {len(self._gemini.keys)} | Groq keys: {len(self._groq.keys)}")

    # ── Non-streaming call ────────────────────────────────────────────────────

    async def call(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        priority: int = 2,
        temperature: float = 0.1,
        max_tokens: int = 4000,
        response_format: Optional[Dict[str, Any]] = None,
        allow_fallback: bool = True,
    ) -> Optional[str]:
        result = await self._gemini.call(
            model=model, messages=messages, priority=priority,
            temperature=temperature, max_tokens=max_tokens,
            response_format=response_format, allow_fallback=allow_fallback,
        )

        if _is_rate_limited(result) and allow_fallback:
            groq_model = _groq_model(model)
            print(f"[FallbackProxy] Gemini exhausted → falling back to Groq ({groq_model})")
            result = await self._groq.call(
                model=groq_model, messages=messages, priority=priority,
                temperature=temperature, max_tokens=max_tokens,
                response_format=response_format,
            )

        return result

    # ── Streaming ─────────────────────────────────────────────────────────────

    async def stream(
        self,
        messages: List[Dict[str, Any]],
        user_query: str = "",
        interrupt_event: Optional[asyncio.Event] = None,
        temperature: float = 0.75,
        max_tokens: int = 3500,
    ) -> AsyncGenerator[str, None]:
        """
        Tries Gemini stream first. If the first chunk is a RATE_LIMIT sentinel
        (or nothing comes back), switches to Groq stream transparently.
        """
        chunks: List[str] = []
        rate_limited = False

        async for chunk in self._gemini.stream(
            messages=messages, user_query=user_query,
            interrupt_event=interrupt_event,
            temperature=temperature, max_tokens=max_tokens,
        ):
            if chunk.startswith("RATE_LIMIT:"):
                rate_limited = True
                break
            chunks.append(chunk)

        if not rate_limited and chunks:
            for c in chunks:
                yield c
            return

        # Gemini was exhausted — route to Groq
        groq_model = _groq_model(CHAT_MODEL)
        print(f"[FallbackProxy] Gemini stream exhausted → falling back to Groq ({groq_model})")
        async for chunk in self._groq.stream(
            messages=messages, user_query=user_query,
            interrupt_event=interrupt_event,
            temperature=temperature, max_tokens=max_tokens,
        ):
            yield chunk

    # ── Chat ─────────────────────────────────────────────────────────────────

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        user_query: str = "",
        temperature: float = 0.1,
        max_tokens: int = 500,
    ) -> str:
        result = await self._gemini.chat(
            messages=messages, user_query=user_query,
            temperature=temperature, max_tokens=max_tokens,
        )
        if not result or result.startswith("RATE_LIMIT:"):
            groq_model = _groq_model(CHAT_MODEL)
            print(f"[FallbackProxy] Gemini chat exhausted → Groq ({groq_model})")
            result = await self._groq.chat(
                messages=messages, user_query=user_query,
                temperature=temperature, max_tokens=max_tokens,
            )
        return result or ""

    # ── STT (always Groq — Gemini uses Groq for STT anyway) ──────────────────

    async def transcribe(
        self,
        file_tuple: tuple,
        model: str = "whisper-large-v3-turbo",
        response_format: str = "text",
    ) -> Optional[str]:
        return await self._gemini.transcribe(
            file_tuple=file_tuple, model=model, response_format=response_format
        )
