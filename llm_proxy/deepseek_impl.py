import time
import re
import asyncio
from typing import AsyncGenerator, Optional, List, Dict, Any

from openai import AsyncOpenAI
from llm_proxy.base import BaseLLMProxy
from config import DEEPSEEK_API_KEY, STT_MODEL

def _sanitize_text_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Ensures messages content passed to DeepSeek API are pure string representations.
    Strips image_url components and joins text blocks to prevent 400 deserialization errors.
    Preserves tool_calls, tool_call_id, and name.
    """
    clean_msgs = []
    for msg in messages:
        clean_msg = {"role": msg.get("role", "user")}
        content = msg.get("content", "")
        if isinstance(content, list):
            text_parts = []
            for part in content:
                if isinstance(part, str):
                    text_parts.append(part)
                elif isinstance(part, dict):
                    if part.get("type") == "text":
                        text_parts.append(part.get("text", ""))
            clean_content = "\n".join(text_parts).strip()
        else:
            clean_content = str(content) if content is not None else ""

        clean_msg["content"] = clean_content

        if "tool_calls" in msg:
            clean_msg["tool_calls"] = msg["tool_calls"]
        if "tool_call_id" in msg:
            clean_msg["tool_call_id"] = msg["tool_call_id"]
        if "name" in msg:
            clean_msg["name"] = msg["name"]

        clean_msgs.append(clean_msg)
    return clean_msgs

def _strip_think_tags(text: str) -> str:
    """Removes DeepSeek reasoning tags <think>...</think> from response text."""
    if not text:
        return ""
    cleaned = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    cleaned = re.sub(r'<think>.*$', '', cleaned, flags=re.DOTALL) # Handle unclosed think tag
    return cleaned.strip()

class DeepSeekProxyImpl(BaseLLMProxy):
    """
    Implementation for DeepSeek API using openai python client.
    Handles multimodal sanitation, vision fallback, and reasoning tag filtering.
    """
    def __init__(self, api_keys: List[str] = None):
        key = (api_keys[0] if api_keys else None) or DEEPSEEK_API_KEY
        if not key:
            raise ValueError("No DEEPSEEK_API_KEY configured.")

        self.keys = api_keys or [key]
        self.client = AsyncOpenAI(
            api_key=key,
            base_url="https://api.deepseek.com"
        )


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
        # Detect vision payloads
        is_vision = False
        for msg in messages:
            if isinstance(msg.get("content"), list):
                for part in msg["content"]:
                    if isinstance(part, dict) and part.get("type") == "image_url":
                        is_vision = True
                        break

        if is_vision:
            from groq import AsyncGroq
            from config import GROQ_API_KEYS, VISION_MODEL
            if not GROQ_API_KEYS:
                print("[DeepSeekProxy] No GROQ_API_KEYS available for Vision fallback.")
                return None
            try:
                vision_client = AsyncGroq(api_key=GROQ_API_KEYS[0])
                kwargs_vision = dict(
                    model=VISION_MODEL,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens
                )
                if timeout is not None:
                    kwargs_vision["timeout"] = timeout
                response = await vision_client.chat.completions.create(**kwargs_vision)
                text = response.choices[0].message.content or ""
                return _strip_think_tags(text.strip())
            except Exception as e:
                print(f"[DeepSeekProxy] Fallback Vision error: {e}")
                return None

        # Route to Groq for non-DeepSeek text models (e.g., Llama 3)
        if "deepseek" not in model.lower() and not is_vision:
            from groq import AsyncGroq
            from config import GROQ_API_KEYS
            if not GROQ_API_KEYS:
                print(f"[DeepSeekProxy] No GROQ_API_KEYS available for fallback text model {model}.")
                return None
            try:
                groq_client = AsyncGroq(api_key=GROQ_API_KEYS[0])
                kwargs_groq = dict(
                    model=model,
                    messages=_sanitize_text_messages(messages),
                    temperature=temperature,
                    max_tokens=max_tokens
                )
                if response_format:
                    kwargs_groq["response_format"] = response_format
                if tools:
                    kwargs_groq["tools"] = tools
                if timeout is not None:
                    kwargs_groq["timeout"] = timeout
                response = await groq_client.chat.completions.create(**kwargs_groq)

                # Support tools via Groq too
                msg = response.choices[0].message
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    return msg

                text = msg.content or ""
                if response_format and response_format.get("type") == "json_object":
                    match = re.search(r'\{.*\}', text, re.DOTALL)
                    if match:
                        text = match.group(0)
                    else:
                        text = text.strip()
                return text.strip()
            except Exception as e:
                print(f"[DeepSeekProxy] Groq text fallback error: {e}")
                return None

        # Sanitize messages for DeepSeek text API
        clean_messages = _sanitize_text_messages(messages)

        # Mapping model string to standard DeepSeek chat model if custom identifier is passed
        target_model = "deepseek-chat" if "deepseek" in model.lower() else model

        kwargs = dict(model=target_model, messages=clean_messages, temperature=temperature, max_tokens=max_tokens)
        if response_format:
            kwargs["response_format"] = response_format
        if tools:
            kwargs["tools"] = tools
        if timeout is not None:
            kwargs["timeout"] = timeout

        max_retries = 2
        for attempt in range(max_retries):
            try:
                response = await self.client.chat.completions.create(**kwargs)
                message = response.choices[0].message

                # If a tool call is returned, return the raw message object so we can inspect tool_calls
                if hasattr(message, "tool_calls") and message.tool_calls:
                    return message

                text = message.content or ""
                text = _strip_think_tags(text)

                if response_format and response_format.get("type") == "json_object":
                    match = re.search(r'\{.*\}', text, re.DOTALL)
                    if match:
                        text = match.group(0)
                    else:
                        text = text.strip()
                return text
            except Exception as e:
                # Retry on 5xx or connection errors
                if "50" in str(e) or "connect" in str(e).lower() or "timeout" in str(e).lower():
                    print(f"[DeepSeekProxy] Transient LLM error (attempt {attempt+1}/{max_retries}): {e}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(1.0)
                        continue
                print(f"[DeepSeekProxy] LLM error: {e}")
                return None

    async def stream(
        self,
        messages: List[Dict[str, Any]],
        user_query: str = "",
        interrupt_event: Optional[asyncio.Event] = None,
        temperature: float = 0.75,
        max_tokens: int = 3500,
    ) -> AsyncGenerator[str, None]:
        target_model = "deepseek-chat"
        clean_messages = _sanitize_text_messages(messages)
        _SENTENCE_END = re.compile(r'(?<=[.!?])\s+|(?<=[.!?])$')
        _CLAUSE_END   = re.compile(r'(?<=[,;])\s+')

        try:
            stream = await self.client.chat.completions.create(
                model=target_model, messages=clean_messages, temperature=temperature, max_tokens=max_tokens, stream=True
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
                        s = _strip_think_tags(s.strip())
                        if s and not (interrupt_event and interrupt_event.is_set()):
                            yield s
                    buffer = sentences[-1]

            remaining = _strip_think_tags(buffer.strip())
            if remaining and not (interrupt_event and interrupt_event.is_set()):
                for clause in _CLAUSE_END.split(remaining):
                    clause = clause.strip()
                    if clause:
                        yield clause

        except Exception as e:
            print(f"[DeepSeekProxy] Stream error: {e}")
            if not (interrupt_event and interrupt_event.is_set()):
                yield "Sorry, I had a little glitch processing that request."
            return

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        user_query: str = "",
        temperature: float = 0.1,
        max_tokens: int = 500,
    ) -> str:
        result = await self.call(model="deepseek-chat", messages=messages, temperature=temperature, max_tokens=max_tokens)
        return result or ""

    async def transcribe(
        self,
        file_tuple: tuple,
        model: str = STT_MODEL,
        response_format: str = "text",
    ) -> Optional[str]:
        from groq import AsyncGroq
        from config import GROQ_API_KEYS

        if not GROQ_API_KEYS:
            print("[DeepSeekProxy] No GROQ_API_KEYS available for STT fallback.")
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
            print(f"[DeepSeekProxy] Fallback STT error: {e}")
            return None

    async def close(self):
        """Close underlying AsyncOpenAI HTTP client cleanly."""
        try:
            if hasattr(self.client, "close"):
                await self.client.close()
        except Exception:
            pass
