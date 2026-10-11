"""Explicit settings loading; no environment, client, or store work at import."""

from dataclasses import dataclass, field
import os
import hashlib
from pathlib import Path
from typing import Mapping
from urllib.parse import urlsplit


class SettingsError(ValueError):
    """Messages identify fields, never their potentially sensitive values."""


@dataclass(frozen=True)
class RoleSettings:
    provider: str
    model: str


@dataclass(frozen=True)
class Settings:
    reasoning: RoleSettings
    extraction: RoleSettings
    voice: RoleSettings
    embeddings: RoleSettings
    data_dir: Path
    legacy_memory_dir: Path
    profile_path: Path
    persona_path: Path
    m2_endpoint: str | None = field(repr=False)
    openrouter_api_key: str = field(default="", repr=False)
    openai_api_key: str = field(default="", repr=False)
    google_api_key: str = field(default="", repr=False)


def _overlap(left: Path, right: Path) -> bool:
    return left == right or left in right.parents or right in left.parents


def _endpoint(value: str) -> str | None:
    if not value:
        return None
    try:
        parsed = urlsplit(value)
        port = parsed.port
        valid = (
            parsed.scheme in {"http", "https"} and parsed.hostname
            and not parsed.username and not parsed.password
            and not parsed.query and not parsed.fragment
            and (port is None or port > 0)
            and not any(c.isspace() for c in value)
        )
    except ValueError:
        valid = False
    if not valid:
        raise SettingsError("SADAF_M2_ENDPOINT must be an HTTP(S) URL without credentials, query, or fragment")
    return value


def load_settings(
    *, root: Path | None = None, environ: Mapping[str, str] | None = None,
    env_file: Path | None = None, read_dotenv: bool = True,
) -> Settings:
    """Read only the explicitly rooted .env, without mutating os.environ.

    Pass read_dotenv=False and an explicit mapping for hermetic fixtures.
    Resolving paths checks symlink aliases without creating directories.
    """
    root = (root or Path.cwd()).resolve()
    values: dict[str, str] = {}
    if read_dotenv:
        from dotenv import dotenv_values

        values.update({k: v for k, v in dotenv_values(
            env_file or root / ".env", interpolate=False,
        ).items() if v is not None})
    values.update(os.environ if environ is None else environ)

    def get(name: str, default: str = "") -> str:
        return values.get(name, default).strip()

    roles = {}
    for role, allowed, default, model, openrouter_model in (
        ("reasoning", {"fake", "openrouter"}, "fake", "synthetic-reasoning", "deepseek/deepseek-v4.1-flash:floor"),
        ("extraction", {"fake", "openrouter"}, "fake", "synthetic-extraction", "deepseek/deepseek-v4.1-flash:floor"),
        ("voice", {"disabled", "fake", "openai", "openrouter"}, "disabled", "", "qwen/qwen-audio-3.0-tts-flash"),
        ("embeddings", {"disabled", "fake", "google"}, "disabled", "", ""),
    ):
        prefix = "SADAF_" + role.upper()
        provider = get(prefix + "_PROVIDER", default)
        if provider not in allowed:
            raise SettingsError(prefix + "_PROVIDER is unsupported")
        selected_model = get(prefix + "_MODEL", model if provider == default else
                             openrouter_model if provider == "openrouter" else "")
        if provider != "disabled" and not selected_model:
            raise SettingsError(prefix + "_MODEL is required for the selected provider")
        key = {"openrouter": "OPENROUTER_API_KEY", "openai": "OPENAI_API_KEY",
               "google": "GOOGLE_API_KEY"}.get(provider)
        if key and not get(key):
            raise SettingsError(key + " is required for the selected provider")
        roles[role] = RoleSettings(provider, selected_model)

    def path(name: str, default: Path | str) -> Path:
        raw = get(name, str(default))
        if not raw:
            raise SettingsError(name + " must be nonempty")
        try:
            return (root / Path(raw).expanduser()).resolve()
        except (OSError, ValueError, RuntimeError):
            raise SettingsError(name + " must be a valid path") from None

    data = path("SADAF_DATA_DIR", ".sadaf-dev")
    legacy = path("SADAF_LEGACY_MEMORY_DIR", "memories")
    if data.exists() and not data.is_dir():
        raise SettingsError("SADAF_DATA_DIR must be a directory")
    # Protect the actual legacy directory even if its setting is overridden.
    if _overlap(data, legacy) or _overlap(data, (root / "memories").resolve()):
        raise SettingsError("SADAF_DATA_DIR must be separate from legacy memories")
    profile = path("SADAF_PROFILE_PATH", data / "profiles" / "{user_id}.md")
    persona = path("SADAF_PERSONA_PATH", data / "persona.md")
    if any(p == data or data not in p.parents for p in (profile, persona)):
        raise SettingsError("Profile and persona paths must be inside SADAF_DATA_DIR")
    if _overlap(profile, persona):
        raise SettingsError("Profile and persona paths must be separate")
    if "{user_id}" in str(profile):
        default_profile=Path(str(profile).replace("{user_id}","default-"+hashlib.sha256(b"default").hexdigest()[:8]))
        if default_profile.is_symlink() or (default_profile.exists() and not default_profile.is_file()) or data not in default_profile.resolve().parents:
            raise SettingsError("Profile paths must be files inside SADAF_DATA_DIR")
        if default_profile.resolve()==persona:
            raise SettingsError("Profile and persona paths must be separate")
    if any(p.exists() and not p.is_file() for p in (profile, persona)):
        raise SettingsError("Profile and persona paths must be files")
    return Settings(**roles, data_dir=data, legacy_memory_dir=legacy,
                    profile_path=profile, persona_path=persona,
                    m2_endpoint=_endpoint(get("SADAF_M2_ENDPOINT")),
                    openrouter_api_key=get("OPENROUTER_API_KEY"),
                    openai_api_key=get("OPENAI_API_KEY"), google_api_key=get("GOOGLE_API_KEY"))
