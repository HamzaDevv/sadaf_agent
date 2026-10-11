"""OpenRouter Qwen ASR adapter using the documented base64 JSON request."""
import asyncio
import base64
import json
from typing import Callable, Mapping


def _http_transport(url: str, headers: Mapping[str, str], data: bytes, timeout: float):
    from urllib.error import HTTPError
    from urllib.request import Request, urlopen
    request = Request(url, data=data, headers=dict(headers), method="POST")
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.status, response.read()
    except HTTPError as error:
        return error.code, error.read()


async def transcribe_qwen_asr(
    file_tuple: tuple, api_key: str, *, model: str = "qwen/qwen3-asr-0.6b",
    timeout: float = 45, transport: Callable | None = None,
) -> str | None:
    """Transcribe a file tuple without sending any non-audio conversation data."""
    if not api_key:
        raise ValueError("OpenRouter API key is required for transcription")
    if not 1 <= timeout <= 120:
        raise ValueError("Transcription timeout must be between 1 and 120 seconds")
    try:
        filename, file_data = file_tuple[0], file_tuple[1]
    except (TypeError, IndexError):
        raise ValueError("Audio must be provided as a filename and bytes tuple") from None
    if hasattr(file_data, "read"):
        file_data = file_data.read()
    if not isinstance(file_data, bytes) or not file_data:
        raise ValueError("Audio fixture must contain nonempty bytes")
    fmt = str(filename).rsplit(".", 1)[-1].lower() if "." in str(filename) else "wav"
    if fmt not in {"wav", "mp3", "flac", "m4a", "ogg", "webm", "aac"}:
        raise ValueError("Unsupported audio file format")
    payload = json.dumps({"model": model, "input_audio": {
        "data": base64.b64encode(file_data).decode("ascii"), "format": fmt,
    }}).encode("utf-8")
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    send = transport or _http_transport
    status, body = await asyncio.to_thread(
        send, "https://openrouter.ai/api/v1/audio/transcriptions", headers, payload, timeout,
    )
    if status < 200 or status >= 300:
        raise RuntimeError(f"OpenRouter transcription returned HTTP {status}")
    try:
        result = json.loads(body)
    except (ValueError, TypeError):
        raise RuntimeError("OpenRouter transcription returned invalid JSON") from None
    text = result.get("text") if isinstance(result, dict) else None
    if not isinstance(text, str):
        raise RuntimeError("OpenRouter transcription response has no text")
    return text.strip() or None
