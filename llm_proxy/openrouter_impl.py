"""OpenRouter compatibility proxy for the legacy application loop."""
from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncGenerator, Dict, List, Optional

from config import OPENROUTER_API_KEY, STT_MODEL
from llm_proxy.base import BaseLLMProxy


class OpenRouterProxyImpl(BaseLLMProxy):
    """Uses OpenRouter's OpenAI-compatible chat and audio-transcription APIs."""

    def __init__(self, api_key: str | None = None, *, client: Any = None):
        key = api_key or OPENROUTER_API_KEY
        if client is None and not key:
            raise ValueError("No OPENROUTER_API_KEY configured.")
        if client is None:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(
                api_key=key,
                base_url="https://openrouter.ai/api/v1",
                default_headers={"HTTP-Referer": "https://github.com/Sadaf-BOT/Sadaf_2", "X-Title": "Sadaf"},
            )
        self.client = client
        self._api_key = key

    async def call(self, model: str, messages: List[Dict[str, Any]], priority: int = 2,
                   temperature: float = 0.1, max_tokens: int = 4000,
                   response_format: Optional[Dict[str, Any]] = None,
                   allow_fallback: bool = True, tools: Optional[List[Dict[str, Any]]] = None,
                   timeout: Optional[float] = None) -> Optional[Any]:
        kwargs: dict[str, Any] = {"model": model, "messages": messages, "max_tokens": max_tokens}
        if temperature is not None: kwargs["temperature"] = temperature
        if response_format: kwargs["response_format"] = response_format
        if tools: kwargs["tools"] = tools
        if timeout is not None: kwargs["timeout"] = timeout
        try:
            response = await self.client.chat.completions.create(**kwargs)
            message = response.choices[0].message
            if getattr(message, "tool_calls", None): return message
            return (message.content or "").strip()
        except Exception:
            # Avoid logging prompts, credentials, or raw provider error bodies.
            return None

    async def stream(self, messages: List[Dict[str, Any]], user_query: str = "",
                     interrupt_event: Optional[asyncio.Event] = None,
                     temperature: float = 0.75, max_tokens: int = 3500) -> AsyncGenerator[str, None]:
        from config import CHAT_MODEL
        try:
            response = await self.client.chat.completions.create(
                model=CHAT_MODEL, messages=messages, temperature=temperature,
                max_tokens=max_tokens, stream=True,
            )
            async for chunk in response:
                if interrupt_event and interrupt_event.is_set(): return
                choices = getattr(chunk, "choices", ())
                if choices:
                    text = getattr(getattr(choices[0], "delta", None), "content", None)
                    if text: yield text
        except Exception:
            if not (interrupt_event and interrupt_event.is_set()):
                yield "Sorry, I couldn't reach the conversation service."

    async def chat(self, messages: List[Dict[str, Any]], user_query: str = "",
                   temperature: float = 0.1, max_tokens: int = 500) -> str:
        from config import CHAT_MODEL
        return await self.call(CHAT_MODEL, messages, temperature=temperature, max_tokens=max_tokens) or ""

    async def transcribe(self, file_tuple: tuple, model: str = STT_MODEL,
                         response_format: str = "text") -> Optional[str]:
        if model.startswith("qwen/qwen3-asr"):
            from sadaf.asr import transcribe_qwen_asr
            return await transcribe_qwen_asr(file_tuple, self._api_key, model=model)
        try:
            result = await self.client.audio.transcriptions.create(
                file=file_tuple, model=model, response_format=response_format,
            )
            return str(result).strip()
        except Exception:
            return None

    async def close(self):
        await self.client.close()


class OpenRouterTTSSynthesizer:
    """Optional paid TTS adapter. It does not enable itself or play returned audio."""
