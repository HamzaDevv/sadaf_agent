import asyncio
import time
from abc import ABC, abstractmethod
from typing import AsyncGenerator, Optional, List, Dict, Any

from config import PROXY_BURST_RESERVE_FRACTION

def is_small_model(model: str) -> bool:
    return "8b" in model or "instant" in model or "lite" in model or "mini" in model

class TokenBucket:
    """
    Leaky-bucket / token-refill pacing for LLM TPM limits.

    Goal: spread burst traffic smoothly across the 60-second window so quota
    is consumed evenly rather than all at once (which causes wall-of-429s).
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
            self._tokens = max(0.0, self._tokens - tokens)

        return wait_s

    def refund(self, tokens: int):
        """
        Return over-reserved tokens to the bucket after the real response arrives.
        Called with (estimated - actual_tokens) so the bucket isn't artificially drained.
        """
        async def _refund():
            async with self._lock:
                self._refill()
                self._tokens = min(self.capacity, self._tokens + tokens)
        asyncio.create_task(_refund())

    def server_correct(self, server_remaining: int):
        """
        Correct our local estimate using the authoritative server header.
        Bidirectional: trusts the server value whether it's higher or lower than
        our local estimate. This lets refunds actually take effect when the server
        confirms more tokens remain than we thought.
        """
        async def _correct():
            async with self._lock:
                self._refill()
                # Blend towards server value (don't blindly overwrite — smooth it)
                self._tokens = float(server_remaining)
        asyncio.create_task(_correct())

    def estimate_tokens(self) -> float:
        """Current estimated available tokens (after virtual refill)."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        return min(self.capacity, self._tokens + elapsed * self.refill_rate)


class BaseKeyState(ABC):
    """Abstract base class for tracking the rate-limit state for a single API key."""
    def __init__(self, key: str):
        self.key = key
        self.locked_until: float = 0.0

    @abstractmethod
    def is_available(self, model: str) -> bool:
        pass

    @abstractmethod
    def available_tokens(self, model: str) -> int:
        pass

    @abstractmethod
    def update_from_headers(self, headers: dict, model: str):
        pass

    @abstractmethod
    def decrement_rpm(self, model: str):
        pass

    @abstractmethod
    def reset_estimates(self):
        pass

    def lock(self, seconds: float):
        self.locked_until = time.monotonic() + seconds
        print(f"[Proxy] Key ...{self.key[-6:]} locked for {seconds:.1f}s")


class BaseLLMProxy(ABC):
    """
    Abstract base class for LLM Proxies.
    Defines the contract for interacting with AI models in Sadaf.
    """

    @abstractmethod
    async def call(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        priority: int = 2,
        temperature: float = 0.1,
        max_tokens: int = 4000,
        response_format: Optional[Dict[str, Any]] = None,
        allow_fallback: bool = True,
        tools: Optional[List[Dict[str, Any]]] = None,
        timeout: Optional[float] = None,
    ) -> Optional[Any]:
        """Non-streaming LLM call (returns text content or message object if tool_calls present)."""
        pass

    @abstractmethod
    async def stream(
        self,
        messages: List[Dict[str, Any]],
        user_query: str = "",
        interrupt_event: Optional[asyncio.Event] = None,
        temperature: float = 0.75,
        max_tokens: int = 3500,
    ) -> AsyncGenerator[str, None]:
        """Streaming chat."""
        # Yield is required here to make it a generator type signature-wise
        yield ""

    @abstractmethod
    async def chat(
        self,
        messages: List[Dict[str, Any]],
        user_query: str = "",
        temperature: float = 0.1,
        max_tokens: int = 500,
    ) -> str:
        """Non-streaming chat call with automatic model selection."""
        pass

    @abstractmethod
    async def transcribe(
        self,
        file_tuple: tuple,
        model: str,
        response_format: str = "text",
    ) -> Optional[str]:
        """Transcribe audio (STT)."""
        pass

    async def close(self):
        """Close any underlying HTTP clients. Override in subclasses that manage connections."""
        pass
