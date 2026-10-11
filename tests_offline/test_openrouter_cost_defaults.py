import asyncio
import json
from sadaf.settings import load_settings
from sadaf.tts import OpenRouterTTSSynthesizer


def test_openrouter_role_defaults_remain_offline_but_select_cheap_model(tmp_path):
    settings = load_settings(root=tmp_path, read_dotenv=False, environ={
        "SADAF_REASONING_PROVIDER": "openrouter",
        "SADAF_EXTRACTION_PROVIDER": "openrouter",
        "OPENROUTER_API_KEY": "fixture-key",
    })
    assert settings.reasoning.model == "deepseek/deepseek-v4.1-flash:floor"
    assert settings.extraction.model == settings.reasoning.model
    assert settings.voice.provider == "disabled"


def test_openrouter_voice_role_is_explicit_opt_in(tmp_path):
    settings = load_settings(root=tmp_path, read_dotenv=False, environ={
        "SADAF_VOICE_PROVIDER": "openrouter",
        "OPENROUTER_API_KEY": "fixture-key",
    })
    assert settings.voice.model == "qwen/qwen-audio-3.0-tts-flash"


def test_tts_sends_fixture_request_and_returns_audio_only():
    seen = []

    def transport(url, headers, data, timeout):
        seen.append((url, headers, json.loads(data), timeout))
        return 200, b"fixture-mp3"

    tts = OpenRouterTTSSynthesizer("fixture-key", transport=transport)
    assert asyncio.run(tts.synthesize("synthetic phrase")) == b"fixture-mp3"
    url, headers, payload, timeout = seen[0]
    assert url.endswith("/audio/speech")
    assert headers["Authorization"] == "Bearer fixture-key"
    assert payload == {"model": "qwen/qwen-audio-3.0-tts-flash", "input": "synthetic phrase",
                       "voice": "loongjohn", "response_format": "mp3"}
    assert timeout == 30


def test_tts_refuses_empty_input_and_unknown_voice():
    import pytest
    tts = OpenRouterTTSSynthesizer("fixture-key", transport=lambda *args: pytest.fail("network path"))
    with pytest.raises(ValueError): asyncio.run(tts.synthesize("  "))
    with pytest.raises(ValueError): OpenRouterTTSSynthesizer("fixture-key", voice="unknown")
