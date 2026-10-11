import asyncio
import base64
import json

import pytest

from sadaf.asr import transcribe_qwen_asr


def test_qwen_asr_uses_base64_json_without_response_format_or_transcript_context():
    calls = []
    def transport(url, headers, body, timeout):
        calls.append((url, headers, json.loads(body), timeout))
        return 200, b'{"text":"Synthetic Kilo Seven"}'
    result = asyncio.run(transcribe_qwen_asr(("short.wav", b"fixture-audio"), "fake-key", transport=transport))
    url, headers, payload, timeout = calls[0]
    assert result == "Synthetic Kilo Seven"
    assert url.endswith("/audio/transcriptions")
    assert headers["Authorization"] == "Bearer fake-key"
    assert payload == {"model":"qwen/qwen3-asr-0.6b", "input_audio":{
        "data":base64.b64encode(b"fixture-audio").decode(), "format":"wav"}}
    assert "response_format" not in payload and timeout == 45


def test_qwen_asr_rejects_bad_files_and_provider_errors():
    with pytest.raises(ValueError, match="nonempty"):
        asyncio.run(transcribe_qwen_asr(("empty.wav", b""), "fake-key"))
    with pytest.raises(RuntimeError, match="HTTP 400"):
        asyncio.run(transcribe_qwen_asr(("short.wav", b"fixture"), "fake-key",
            transport=lambda *args: (400, b"untrusted provider body")))
