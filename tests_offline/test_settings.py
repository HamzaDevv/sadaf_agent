import os
from pathlib import Path

import pytest

from sadaf.settings import SettingsError, load_settings


def settings(tmp_path, **values):
    return load_settings(root=tmp_path, environ=values, read_dotenv=False)


def test_no_keys_no_writes(tmp_path):
    result = settings(tmp_path)
    assert result.reasoning.provider == result.extraction.provider == "fake"
    assert result.voice.provider == result.embeddings.provider == "disabled"
    assert result.data_dir == tmp_path / ".sadaf-dev"
    assert not list(tmp_path.iterdir())


def test_explicit_dotenv_environment_precedence_and_redaction(tmp_path):
    env = tmp_path / ".env"
    env.write_text("OPENROUTER_API_KEY=fixture-secret\nSADAF_REASONING_PROVIDER=openrouter\n"
                   "SADAF_REASONING_MODEL=fixture/model\n", encoding="utf-8")
    before = dict(os.environ)
    result = load_settings(root=tmp_path, environ={"OPENROUTER_API_KEY": "override-secret"})
    assert result.openrouter_api_key == "override-secret"
    assert result.reasoning.model == "fixture/model"
    assert "secret" not in repr(result)
    assert dict(os.environ) == before
    assert load_settings(root=tmp_path, environ={}, read_dotenv=False).reasoning.provider == "fake"


@pytest.mark.parametrize("field,value", [
    ("SADAF_REASONING_PROVIDER", "unknown-sensitive-value"),
    ("SADAF_EXTRACTION_MODEL", ""),
    ("SADAF_VOICE_PROVIDER", "openrouter"),
    ("SADAF_EMBEDDINGS_PROVIDER", "openai"),
    ("SADAF_DATA_DIR", ""),
    ("SADAF_DATA_DIR", "memories"),
    ("SADAF_DATA_DIR", "memories/nested"),
    ("SADAF_DATA_DIR", "."),
    ("SADAF_PROFILE_PATH", "memories/profile.md"),
    ("SADAF_M2_ENDPOINT", "ftp://fixture.invalid"),
    ("SADAF_M2_ENDPOINT", "https://secret:secret@fixture.invalid"),
    ("SADAF_M2_ENDPOINT", "https://fixture.invalid/?key=secret"),
    ("SADAF_M2_ENDPOINT", "https://fixture.invalid/#secret"),
    ("SADAF_M2_ENDPOINT", "http://fixture.invalid:invalid"),
    ("SADAF_M2_ENDPOINT", "http://fixture.invalid:0"),
])
def test_invalid_fields_have_safe_errors(tmp_path, field, value):
    with pytest.raises(SettingsError) as error:
        settings(tmp_path, **{field: value})
    assert "secret" not in str(error.value)
    assert "sensitive-value" not in str(error.value)


@pytest.mark.parametrize("role,provider,key", [
    ("REASONING", "openrouter", "OPENROUTER_API_KEY"),
    ("EXTRACTION", "openrouter", "OPENROUTER_API_KEY"),
    ("VOICE", "openai", "OPENAI_API_KEY"),
    ("EMBEDDINGS", "google", "GOOGLE_API_KEY"),
])
def test_live_roles_validate_model_and_credential_separately(tmp_path, role, provider, key):
    values = {f"SADAF_{role}_PROVIDER": provider}
    if provider == "openrouter":
        result = settings(tmp_path, **{**values, key:"fixture-secret"})
        assert result.reasoning.model == "openai/gpt-6.1-sol" if role == "REASONING" else result.extraction.model == "openai/gpt-6-luna"
    else:
        with pytest.raises(SettingsError, match=f"SADAF_{role}_MODEL"):
            settings(tmp_path, **values)
        values[f"SADAF_{role}_MODEL"] = "fixture/model"
    with pytest.raises(SettingsError, match=key):
        settings(tmp_path, **values)
    values[key] = "fixture-secret"
    result = settings(tmp_path, **values)
    assert getattr(result, role.lower()).provider == provider


def test_data_symlink_cannot_alias_legacy(tmp_path):
    (tmp_path / "memories").mkdir()
    (tmp_path / "alias").symlink_to(tmp_path / "memories", target_is_directory=True)
    with pytest.raises(SettingsError, match="separate"):
        settings(tmp_path, SADAF_DATA_DIR="alias")
    with pytest.raises(SettingsError, match="separate"):
        settings(tmp_path, SADAF_DATA_DIR="memories", SADAF_LEGACY_MEMORY_DIR="other")


def test_profile_symlink_cannot_escape(tmp_path):
    (tmp_path / ".sadaf-dev").mkdir()
    (tmp_path / ".sadaf-dev/profiles/default-37a8eec1.md").parent.mkdir(parents=True)
    (tmp_path / ".sadaf-dev/profiles/default-37a8eec1.md").symlink_to(tmp_path / "outside.md")
    with pytest.raises(SettingsError, match="inside"):
        settings(tmp_path, SADAF_PROFILE_PATH=".sadaf-dev/profiles/{user_id}.md")


def test_profile_template_cannot_collide_with_persona(tmp_path):
    with pytest.raises(SettingsError,match="separate"):
        settings(tmp_path,SADAF_PERSONA_PATH=".sadaf-dev/profiles/default-37a8eec1.md")


def test_role_and_path_overrides_are_independent(tmp_path):
    result = settings(tmp_path, SADAF_REASONING_MODEL="fixture/main",
                      SADAF_EXTRACTION_MODEL="fixture/extract", SADAF_DATA_DIR="fixture-data",
                      SADAF_M2_ENDPOINT="http://localhost:9000/service")
    assert result.reasoning.model != result.extraction.model
    assert result.profile_path == tmp_path / "fixture-data/profiles/{user_id}.md"
    assert result.persona_path == tmp_path / "fixture-data/persona.md"
    assert result.m2_endpoint == "http://localhost:9000/service"


def test_existing_data_file_is_rejected(tmp_path):
    (tmp_path / ".sadaf-dev").write_text("fixture")
    with pytest.raises(SettingsError, match="directory"):
        settings(tmp_path)


def test_existing_profile_directory_is_rejected(tmp_path):
    (tmp_path / ".sadaf-dev/profiles/default-37a8eec1.md").mkdir(parents=True)
    with pytest.raises(ValueError, match="must be files"):
        from sadaf.memory import MemoryStore
        MemoryStore(tmp_path / ".sadaf-dev/memory.sqlite3")
