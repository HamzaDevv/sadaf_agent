from typing import List, Dict, Any, Optional, AsyncGenerator
import asyncio

from llm_proxy.base import BaseLLMProxy

class DeepSeekProxyImpl(BaseLLMProxy):
    """
    Stub implementation for DeepSeek API.
    Designed to show future scalability of the new proxy architecture.
    """
    def __init__(self, api_keys: List[str] = None):
        print("[DeepSeekProxy] Initialized (Stub)")

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
        print("[DeepSeekProxy] call() is not implemented.")
        return None

    async def stream(
        self,
        messages: List[Dict[str, Any]],
        user_query: str = "",
        interrupt_event: Optional[asyncio.Event] = None,
        temperature: float = 0.75,
        max_tokens: int = 3500,
    ) -> AsyncGenerator[str, None]:
        print("[DeepSeekProxy] stream() is not implemented.")
        yield "DeepSeek proxy is a stub."

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        user_query: str = "",
        temperature: float = 0.1,
        max_tokens: int = 500,
    ) -> str:
        return "[DeepSeekProxy] Not implemented."

    async def transcribe(
        self,
        file_tuple: tuple,
        model: str,
        response_format: str = "text",
    ) -> Optional[str]:
        return None
