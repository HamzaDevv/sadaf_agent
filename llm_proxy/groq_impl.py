import time
import re
import asyncio
from typing import AsyncGenerator, Optional, List, Dict, Any

from groq import AsyncGroq
from llm_proxy.base import BaseKeyState, BaseLLMProxy, TokenBucket, is_small_model
from config import (
    GROQ_API_KEYS, GROQ_TPM_8B, GROQ_TPM_70B, GROQ_RPM,
    PRIORITY_CHAT, PRIORITY_EXTRACTION, PRIORITY_AGENT, STT_MODEL,
    PROXY_SILENT_WAIT_THRESHOLD_S, CHAT_MODEL
)
from config import VERBOSE_LOGS

def _log_verbose(*args, **kwargs):
    if VERBOSE_LOGS:
        import builtins
        builtins.print(*args, **kwargs)

def _parse_reset_duration(value: str) -> float:
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


class GroqKeyState(BaseKeyState):
    def __init__(self, key: str):
        super().__init__(key)
        self.client = AsyncGroq(api_key=key)
        self.reset_estimates()
        self.reset_tokens_at: float = 0.0
        self.reset_requests_at: float = 0.0

    def reset_estimates(self):
        self.remaining_tokens_8b: int = GROQ_TPM_8B
        self.remaining_tokens_70b: int = GROQ_TPM_70B
        self.remaining_requests_8b: int = GROQ_RPM
        self.remaining_requests_70b: int = GROQ_RPM

    def is_available(self, model: str) -> bool:
        now = time.monotonic()
        if now < self.locked_until:
            return False

        rem_req = self.remaining_requests_8b if is_small_model(model) else self.remaining_requests_70b
        if rem_req <= 1:
            if now < self.reset_requests_at:
                return False

        remaining = self.remaining_tokens_8b if is_small_model(model) else self.remaining_tokens_70b
        if remaining <= 100:
            if now < self.reset_tokens_at:
                return False
        return True

    def available_tokens(self, model: str) -> int:
        if not self.is_available(model):
            return 0
        return self.remaining_tokens_8b if is_small_model(model) else self.remaining_tokens_70b

    def update_from_headers(self, headers: dict, model: str):
        try:
            if "x-ratelimit-remaining-tokens" in headers:
                val = int(headers["x-ratelimit-remaining-tokens"])
                if is_small_model(model):
                    self.remaining_tokens_8b = val
                else:
                    self.remaining_tokens_70b = val

            if "x-ratelimit-remaining-requests" in headers:
                val_req = int(headers["x-ratelimit-remaining-requests"])
                if is_small_model(model):
                    self.remaining_requests_8b = val_req
                else:
                    self.remaining_requests_70b = val_req

            if "x-ratelimit-reset-tokens" in headers:
                self.reset_tokens_at = time.monotonic() + _parse_reset_duration(
                    headers["x-ratelimit-reset-tokens"]
                )

            if "x-ratelimit-reset-requests" in headers:
                self.reset_requests_at = time.monotonic() + _parse_reset_duration(
                    headers["x-ratelimit-reset-requests"]
                )
        except Exception as e:
            _log_verbose(f"[GroqProxy] Header parse error: {e}")

    def decrement_rpm(self, model: str):
        if is_small_model(model):
            self.remaining_requests_8b = max(0, self.remaining_requests_8b - 1)
        else:
            self.remaining_requests_70b = max(0, self.remaining_requests_70b - 1)


class GroqProxyImpl(BaseLLMProxy):
    def __init__(self, api_keys: List[str] = None):
        keys = api_keys if api_keys else GROQ_API_KEYS
        if not keys:
            raise ValueError("No GROQ_API_KEYS configured.")
        self.keys: List[GroqKeyState] = [GroqKeyState(k) for k in keys]
        self._rr_index: int = 0
        self._lock = asyncio.Lock()

        # We assume `self.router` will be set dynamically or we can import if needed,
        # but right now we handle `chat` and `stream` which need a router. We'll use a simple mock if none exists.
        # Ideally, `Router` shouldn't be inside the proxy, but we maintain backward compatibility.
        # Lazy loading to prevent circular import
        self._router = None

        n = len(self.keys)
        self._bucket_8b  = TokenBucket(capacity=GROQ_TPM_8B  * n, refill_rate=(GROQ_TPM_8B  * n) / 60.0)
        self._bucket_70b = TokenBucket(capacity=GROQ_TPM_70B * n, refill_rate=(GROQ_TPM_70B * n) / 60.0)

    def _best_key(self, model: str) -> Optional[GroqKeyState]:
        available = [k for k in self.keys if k.is_available(model)]
        if not available:
            return None
        return max(available, key=lambda k: k.available_tokens(model))

    def _next_key(self, model: str) -> Optional[GroqKeyState]:
        for _ in range(len(self.keys)):
            self._rr_index = (self._rr_index + 1) % len(self.keys)
            k = self.keys[self._rr_index]
            if k.is_available(model):
                return k
        return None

    def _select_key(self, model: str) -> Optional[GroqKeyState]:
        return self._best_key(model) or self._next_key(model)

    def _bucket_for(self, model: str) -> TokenBucket:
        return self._bucket_8b if is_small_model(model) else self._bucket_70b

    @staticmethod
    def _estimate_tokens(messages: list[dict], max_tokens: int) -> int:
        prompt_chars = sum(len(m.get("content", "")) for m in messages)
        # Estimate prompt tokens conservatively (char/4), but cap reserved
        # completion budget at 1500 instead of the full max_tokens ceiling.
        # The real usage is refunded after the response arrives.
        return int(prompt_chars / 4) + min(max_tokens, 1500)

    async def call(
        self,
        model: str,
        messages: list[dict],
        priority: int = PRIORITY_EXTRACTION,
        temperature: float = 0.1,
        max_tokens: int = 4000,
        response_format: Optional[dict] = None,
        allow_fallback: bool = True,
        tools: Optional[List[Dict[str, Any]]] = None,
        timeout: Optional[float] = None,
    ) -> Optional[Any]:
        estimated = self._estimate_tokens(messages, max_tokens)
        bucket = self._bucket_for(model)
        wait_s = await bucket.consume(estimated)

        if wait_s >= PROXY_SILENT_WAIT_THRESHOLD_S:
            _log_verbose(f"[GroqProxy] Pacing wait {wait_s:.1f}s for {model}")

        attempts = 0
        last_err = None

        while attempts < min(3, len(self.keys) + 1):
            key_state = self._select_key(model)
            if not key_state:
                wait = 60.0
                _log_verbose(f"[GroqProxy] All keys exhausted for {model}. Waiting {wait}s...")
                await asyncio.sleep(wait)
                for k in self.keys:
                    k.reset_estimates()
                key_state = self.keys[0]

            key_state.decrement_rpm(model)

            kwargs = dict(model=model, messages=messages, temperature=temperature, max_tokens=max_tokens)
            if response_format:
                kwargs["response_format"] = response_format
            if tools:
                kwargs["tools"] = tools
            if timeout is not None:
                kwargs["timeout"] = timeout

            try:
                response = await key_state.client.chat.completions.create(**kwargs)
                try:
                    headers = response._raw_response.headers
                    headers_dict = dict(headers)
                    key_state.update_from_headers(headers_dict, model)
                    if "x-ratelimit-remaining-tokens" in headers_dict:
                        server_remaining = int(headers_dict["x-ratelimit-remaining-tokens"])
                        bucket.server_correct(server_remaining * len(self.keys))
                except Exception:
                    pass

                message = response.choices[0].message
                if hasattr(message, "tool_calls") and message.tool_calls:
                    return message

                text = message.content or ""
                text = text.strip()
                if response_format and response_format.get("type") == "json_object":
                    match = re.search(r'\{.*\}', text, re.DOTALL)
                    if match:
                        text = match.group(0)
                    else:
                        text = text.strip()

                # ── Token refund: return over-reserved tokens to the bucket ──
                try:
                    actual = (response.usage.prompt_tokens or 0) + (response.usage.completion_tokens or 0)
                    overage = max(0, estimated - actual)
                    if overage > 0:
                        bucket.refund(overage)
                except Exception:
                    pass

                return text

            except Exception as e:
                err = str(e)
                last_err = err
                attempts += 1

                if "429" in err or "rate_limit" in err.lower() or "too many requests" in err.lower():
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
                            _log_verbose(f"[GroqProxy] High wait ({retry_after}s) for {model}. Smart fallback to 8b.")
                            model = CHAT_MODEL
                            bucket = self._bucket_for(model)
                            continue
                        else:
                            _log_verbose(f"[GroqProxy] High wait ({retry_after}s) for {model}. No fallback (critical call).")
                            return f"RATE_LIMIT: {err}"

                    key_state.lock(retry_after)
                    _log_verbose(f"[GroqProxy] 429 on key ...{key_state.key[-6:]}. Trying next key.")
                    continue

                _log_verbose(f"[GroqProxy] LLM error (attempt {attempts}): {e}")
                break

        _log_verbose(f"[GroqProxy] All attempts failed: {last_err}")
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
            _log_verbose(f"[GroqProxy] Stream pacing wait {wait_s:.1f}s for {model}")

        attempts = 0
        while attempts < min(3, len(self.keys) + 1):
            key_state = self._select_key(model)
            if not key_state:
                if interrupt_event and interrupt_event.is_set():
                    return
                yield "Give me just a second."
                await asyncio.sleep(60)
                key_state = self.keys[0]

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

                try:
                    headers = stream._raw_response.headers
                    headers_dict = dict(headers)
                    key_state.update_from_headers(headers_dict, model)
                    if "x-ratelimit-remaining-tokens" in headers_dict:
                        server_remaining = int(headers_dict["x-ratelimit-remaining-tokens"])
                        bucket.server_correct(server_remaining * len(self.keys))
                except Exception:
                    pass

                return

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
                if not (interrupt_event and interrupt_event.is_set()):
                    yield "Sorry, I had a little brain glitch there."
                return

    async def chat(self, messages: list[dict], user_query: str = "", temperature: float = 0.1, max_tokens: int = 500) -> str:
        model = self._get_router().select_chat_model(user_query)
        result = await self.call(model=model, messages=messages, priority=PRIORITY_CHAT, temperature=temperature, max_tokens=max_tokens)
        return result or ""

    async def transcribe(self, file_tuple: tuple, model: str = STT_MODEL, response_format: str = "text") -> Optional[str]:
        attempts = 0
        while attempts < len(self.keys):
            key_state = self._select_key(model)
            if not key_state:
                self._rr_index = (self._rr_index + 1) % len(self.keys)
                key_state = self.keys[self._rr_index]

            key_state.decrement_rpm(model)

            try:
                result = await key_state.client.audio.transcriptions.create(
                    file=file_tuple, model=model, response_format=response_format
                )
                return str(result).strip()
            except Exception as e:
                err = str(e)
                attempts += 1
                if "429" in err or "rate_limit" in err.lower():
                    key_state.lock(30.0)
                    if is_small_model(model):
                        key_state.remaining_requests_8b = min(GROQ_RPM, key_state.remaining_requests_8b + 1)
                    else:
                        key_state.remaining_requests_70b = min(GROQ_RPM, key_state.remaining_requests_70b + 1)
                    continue
                _log_verbose(f"[GroqProxy] STT error: {e}")
                return None

        _log_verbose("[GroqProxy] All STT attempts failed.")
        return None

    async def close(self):
        """Close all underlying AsyncGroq HTTP clients cleanly."""
        for key_state in self.keys:
            try:
                # AsyncGroq inherits BaseApiClient which exposes aclose()
                if hasattr(key_state.client, "aclose"):
                    await key_state.client.aclose()
                elif hasattr(key_state.client, "close"):
                    await key_state.client.close()
            except Exception:
                pass
