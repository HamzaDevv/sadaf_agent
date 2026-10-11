"""Opt-in OpenRouter TTS adapter; returned audio is not played automatically."""
import asyncio
import json


class OpenRouterTTSSynthesizer:
    endpoint = "https://openrouter.ai/api/v1/audio/speech"
    model = "qwen/qwen-audio-3.0-tts-flash"

    def __init__(self, api_key: str, *, voice: str = "loongjohn", timeout: float = 30,
                 transport=None):
        if not api_key: raise ValueError("OpenRouter API key is required for TTS")
        if voice not in {"loongjohn", "longanhuan_v3.6"}: raise ValueError("Unsupported Qwen TTS voice")
        if timeout <= 0: raise ValueError("timeout must be positive")
        self._key, self.voice, self.timeout = api_key, voice, timeout
        self._transport = transport or self._http_transport

    @staticmethod
    def _http_transport(url: str, headers: dict, data: bytes, timeout: float):
        from urllib.request import Request, urlopen
        request = Request(url, data=data, headers=headers, method="POST")
        with urlopen(request, timeout=timeout) as response:
            return response.status, response.read()

    async def synthesize(self, text: str) -> bytes:
        text = text.strip()
        if not text or len(text) > 4000: raise ValueError("TTS text must contain 1–4000 characters")
        payload = json.dumps({"model": self.model, "input": text, "voice": self.voice,
                              "response_format": "mp3"}).encode()
        headers = {"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"}
        status, audio = await asyncio.to_thread(self._transport, self.endpoint, headers, payload, self.timeout)
        if status < 200 or status >= 300 or not audio:
            raise RuntimeError("OpenRouter TTS request failed")
        return audio
