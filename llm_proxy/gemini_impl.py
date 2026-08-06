import time
import re
import asyncio
import random
from typing import AsyncGenerator, Optional, List, Dict, Any

from openai import AsyncOpenAI
from llm_proxy.base import BaseKeyState, BaseLLMProxy, TokenBucket, is_small_model
from config import (
    GEMINI_API_KEYS, GEMINI_TPM_LITE, GEMINI_TPM_FLASH, GEMINI_RPM_LITE, GEMINI_RPM_FLASH,
    PRIORITY_CHAT, PRIORITY_EXTRACTION, PRIORITY_AGENT, STT_MODEL,
    PROXY_SILENT_WAIT_THRESHOLD_S, CHAT_MODEL, GEMINI_RETRY_LOCK_S
)

class GeminiKeyState(BaseKeyState):
    def __init__(self, key: str):
        super().__init__(key)
        self.client = AsyncOpenAI(
            api_key=key, 
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
        )
        self.reset_estimates()
        
    def reset_estimates(self):
        self.remaining_tokens_lite: int = GEMINI_TPM_LITE
        self.remaining_tokens_flash: int = GEMINI_TPM_FLASH
        self.remaining_requests_lite: int = GEMINI_RPM_LITE
        self.remaining_requests_flash: int = GEMINI_RPM_FLASH

    def is_available(self, model: str) -> bool:
        now = time.monotonic()
        if now < self.locked_until:
            return False
            
        rem_req = self.remaining_requests_lite if is_small_model(model) else self.remaining_requests_flash
        if rem_req <= 1:
            return False
                
        remaining = self.remaining_tokens_lite if is_small_model(model) else self.remaining_tokens_flash
        if remaining <= 100:  
            return False
            
        return True

    def available_tokens(self, model: str) -> int:
        if not self.is_available(model):
            return 0
        return self.remaining_tokens_lite if is_small_model(model) else self.remaining_tokens_flash

    def update_from_headers(self, headers: dict, model: str):
        # Gemini API doesn't expose standard rate limit headers like Groq yet,
        # but we parse if they exist.
        pass

    def decrement_rpm(self, model: str):
        if is_small_model(model):
            self.remaining_requests_lite = max(0, self.remaining_requests_lite - 1)
        else:
            self.remaining_requests_flash = max(0, self.remaining_requests_flash - 1)


class GeminiProxyImpl(BaseLLMProxy):
    def __init__(self, api_keys: List[str] = None):
        keys = api_keys if api_keys else GEMINI_API_KEYS
        if not keys:
            raise ValueError("No GEMINI_API_KEYS configured.")
        self.keys: List[GeminiKeyState] = [GeminiKeyState(k) for k in keys]
        self._rr_index: int = 0
        self._lock = asyncio.Lock()
        
        self._router = None

        n = len(self.keys)
        self._bucket_lite  = TokenBucket(capacity=GEMINI_TPM_LITE  * n, refill_rate=(GEMINI_TPM_LITE  * n) / 60.0)
        self._bucket_flash = TokenBucket(capacity=GEMINI_TPM_FLASH * n, refill_rate=(GEMINI_TPM_FLASH * n) / 60.0)

    def _best_key(self, model: str) -> Optional[GeminiKeyState]:
        available = [k for k in self.keys if k.is_available(model)]
        if not available:
            return None
        return max(available, key=lambda k: k.available_tokens(model))

    def _next_key(self, model: str) -> Optional[GeminiKeyState]:
        for _ in range(len(self.keys)):
            self._rr_index = (self._rr_index + 1) % len(self.keys)
            k = self.keys[self._rr_index]
            if k.is_available(model):
                return k
        return None

    def _select_key(self, model: str) -> Optional[GeminiKeyState]:
        return self._best_key(model) or self._next_key(model)

    def _bucket_for(self, model: str) -> TokenBucket:
        return self._bucket_lite if is_small_model(model) else self._bucket_flash

    @staticmethod
    def _estimate_tokens(messages: list[dict], max_tokens: int) -> int:
        prompt_chars = sum(len(m.get("content", "")) for m in messages)
        return int(prompt_chars / 4) + max_tokens

    async def call(self, model: str, messages: list[dict], priority: int = PRIORITY_EXTRACTION, temperature: float = 0.1, max_tokens: int = 4000, response_format: Optional[dict] = None, allow_fallback: bool = True) -> Optional[str]:
        estimated = self._estimate_tokens(messages, max_tokens)
        bucket = self._bucket_for(model)
        wait_s = await bucket.consume(estimated)

        if wait_s >= PROXY_SILENT_WAIT_THRESHOLD_S:
            print(f"[GeminiProxy] Pacing wait {wait_s:.1f}s for {model}")

        attempts = 0
        last_err = None

        while attempts < len(self.keys) + 1:
            key_state = self._select_key(model)
            if not key_state:
                # Wait until the soonest-unlocking key is ready, plus a small jitter
                now = time.monotonic()
                soonest = min(k.locked_until for k in self.keys)
                wait = max(1.0, soonest - now) + random.uniform(0.5, 3.0)
                print(f"[GeminiProxy] All keys exhausted for {model}. Waiting {wait:.1f}s...")
                await asyncio.sleep(wait)
                # Only reset keys whose lock has actually expired
                now = time.monotonic()
                for k in self.keys:
                    if now >= k.locked_until:
                        k.reset_estimates()
                key_state = self._select_key(model) or self.keys[0]

            key_state.decrement_rpm(model)

            kwargs = dict(model=model, messages=messages, temperature=temperature, max_tokens=max_tokens)
            if response_format:
                kwargs["response_format"] = response_format

            try:
                response = await key_state.client.chat.completions.create(**kwargs)
                
                text = response.choices[0].message.content or ""
                text = text.strip()
                if response_format and response_format.get("type") == "json_object":
                    match = re.search(r'\{.*\}', text, re.DOTALL)
                    if match:
                        text = match.group(0)
                    else:
                        text = text.strip()
                return text

            except Exception as e:
                err = str(e)
                last_err = err
                attempts += 1

                if "429" in err or "rate_limit" in err.lower() or "too many requests" in err.lower():
                    # Lock for a full quota window so we don't immediately re-hit the limit
                    jitter = random.uniform(0.0, 5.0)
                    key_state.lock(GEMINI_RETRY_LOCK_S + jitter)
                    print(f"[GeminiProxy] 429 on key ...{key_state.key[-6:]}. Trying next key.")
                    continue

                print(f"[GeminiProxy] LLM error (attempt {attempts}): {e}")
                break

        print(f"[GeminiProxy] All attempts failed: {last_err}")
        if last_err and ("429" in last_err or "rate_limit" in last_err.lower() or "too many requests" in last_err.lower()):
            return f"RATE_LIMIT: {last_err}"
        return None

    def _get_router(self):
        if self._router is None:
            from brain.pre_processor import IntentRouter
            self._router = IntentRouter()
        return self._router

    async def stream(self, messages: list[dict], user_query: str = "", interrupt_event: Optional[asyncio.Event] = None, temperature: float = 0.75, max_tokens: int = 3500) -> AsyncGenerator[str, None]:
        model = self._get_router().select_chat_model(user_query)
        _SENTENCE_END = re.compile(r'(?<=[.!?])\s+|(?<=[.!?])$')
        _CLAUSE_END   = re.compile(r'(?<=[,;])\s+')

        estimated = self._estimate_tokens(messages, max_tokens)
        bucket = self._bucket_for(model)
        wait_s = await bucket.consume(estimated)
        if wait_s >= PROXY_SILENT_WAIT_THRESHOLD_S:
            print(f"[GeminiProxy] Stream pacing wait {wait_s:.1f}s for {model}")

        attempts = 0
        all_exhausted_once = False
        while attempts < len(self.keys) + 1:
            key_state = self._select_key(model)
            if not key_state:
                if interrupt_event and interrupt_event.is_set():
                    return
                if all_exhausted_once:
                    # Second time around with no keys — signal fallback
                    yield "RATE_LIMIT: all Gemini keys exhausted"
                    return
                # Wait until the soonest-unlocking key is ready, plus jitter
                now = time.monotonic()
                soonest = min(k.locked_until for k in self.keys)
                wait = max(1.0, soonest - now) + random.uniform(0.5, 3.0)
                print(f"[GeminiProxy] All keys exhausted for {model}. Waiting {wait:.1f}s...")
                await asyncio.sleep(wait)
                now = time.monotonic()
                for k in self.keys:
                    if now >= k.locked_until:
                        k.reset_estimates()
                key_state = self._select_key(model) or self.keys[0]
                all_exhausted_once = True

            key_state.decrement_rpm(model)

            try:
                stream = await key_state.client.chat.completions.create(
                    model=model, messages=messages, temperature=temperature, max_tokens=max_tokens, stream=True
                )

                buffer = ""
                in_think = False

                async for chunk in stream:
                    if interrupt_event and interrupt_event.is_set():
                        return

                    delta = chunk.choices[0].delta.content
                    if not delta:
                        continue

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

                remaining = buffer.strip()
                if remaining and not (interrupt_event and interrupt_event.is_set()):
                    for clause in _CLAUSE_END.split(remaining):
                        clause = clause.strip()
                        if clause:
                            yield clause
                return  

            except Exception as e:
                err = str(e)
                attempts += 1
                if "429" in err or "rate_limit" in err.lower():
                    jitter = random.uniform(0.0, 5.0)
                    key_state.lock(GEMINI_RETRY_LOCK_S + jitter)
                    continue
                if not (interrupt_event and interrupt_event.is_set()):
                    yield "Sorry, I had a little brain glitch there."
                return

    async def chat(self, messages: list[dict], user_query: str = "", temperature: float = 0.1, max_tokens: int = 500) -> str:
        model = self._get_router().select_chat_model(user_query)
        result = await self.call(model=model, messages=messages, priority=PRIORITY_CHAT, temperature=temperature, max_tokens=max_tokens)
        return result or ""

    async def transcribe(self, file_tuple: tuple, model: str = STT_MODEL, response_format: str = "text") -> Optional[str]:
        # For Gemini, the old code used Groq API key for STT as a fallback. 
        # So we can instantiate Groq specifically for transcribe if needed,
        # or implement Gemini's audio transcription if available.
        # But for stability, we replicate the old fallback:
        
        from groq import AsyncGroq
        from config import GROQ_API_KEYS
        
        if not GROQ_API_KEYS:
            print("[GeminiProxy] No GROQ_API_KEYS available for STT fallback.")
            return None
            
        stt_client = AsyncGroq(api_key=GROQ_API_KEYS[0])
        try:
            result = await stt_client.audio.transcriptions.create(
                file=file_tuple,
                model=model,
                response_format=response_format,
            )
            return str(result).strip()
        except Exception as e:
            print(f"[GeminiProxy] Fallback STT error: {e}")
            return None
