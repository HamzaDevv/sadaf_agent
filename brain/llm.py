"""
brain/llm.py — Sadaf V4 Streaming LLM Engine

V4 changes:
  - All API calls routed through groq_proxy (multi-key, rate-managed)
  - stream_sentences() delegates fully to groq_proxy.stream()
  - get_full_response() delegates to groq_proxy.chat()
  - Model selection (8b vs 70b) is handled by groq_proxy.ModelRouter
"""
import asyncio
import re
from typing import AsyncGenerator

from groq_proxy import groq_proxy
from utils import strip_think_tags


async def stream_sentences(
    system_prompt: str,
    user_input: str,
    interrupt_event: asyncio.Event,
) -> AsyncGenerator[str, None]:
    """
    Stream sentences from Groq LLM one at a time via the proxy.
    Yields complete sentence chunks for immediate TTS playback.
    Model (8b vs 70b) auto-selected by groq_proxy based on query complexity.
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_input},
    ]
    async for sentence in groq_proxy.stream(
        messages=messages,
        user_query=user_input,
        interrupt_event=interrupt_event,
        temperature=0.75,
        max_tokens=350,
    ):
        yield sentence


async def get_full_response(
    system_prompt: str,
    user_input: str,
) -> str:
    """
    Non-streaming version for memory consolidation (needs full text).
    Always strips think tags from result.
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_input},
    ]
    result = await groq_proxy.chat(
        messages=messages,
        user_query=user_input,
        temperature=0.1,
        max_tokens=500,
    )
    return strip_think_tags(result) if result else ""
