import json
import os
from pathlib import Path
import subprocess
import sys
import tomllib

import pytest

from sadaf.cli import main

ROOT = Path(__file__).resolve().parents[1]


def test_default_pytest_collection_stays_offline():
    config = (ROOT / "pytest.ini").read_text()
    assert "testpaths = tests_offline" in config
    assert "--confcutdir=tests_offline" in config
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert project["project"]["requires-python"] == ">=3.13,<3.14"
    assert all("audio" not in dependency for dependency in project["project"]["dependencies"])
    assert any(dep.startswith("google-genai") for dep in project["project"]["optional-dependencies"]["vector"])
    assert "google-generativeai" not in (ROOT / "requirements.txt").read_text()


def test_imports_and_cli_cannot_reach_legacy_or_network(tmp_path):
    # Synthetic legacy sentinel: hash/mtime and directory inventory must not change.
    legacy = tmp_path / "memories"
    legacy.mkdir()
    sentinel = legacy / "graph.json"
    sentinel.write_text('{"nodes": {"fixture": {"status": "confirmed"}}}')
    before = sentinel.read_bytes(), sentinel.stat().st_mtime_ns
    code = '''
import importlib.abc, socket, sys
class BlockLegacy(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in {"memory", "llm_proxy", "audio", "brain", "tools", "config", "openai", "groq", "google", "chromadb"}:
            raise AssertionError("Forbidden import: " + fullname)
sys.meta_path.insert(0, BlockLegacy())
def blocked(*args, **kwargs):
    raise AssertionError("Forbidden network")
socket.socket.connect = socket.socket.connect_ex = socket.create_connection = socket.getaddrinfo = blocked
import sadaf, sadaf.settings, sadaf.runtime, sadaf.cli
assert sadaf.cli.main(["--no-dotenv", "doctor"]) == 0
assert sadaf.cli.main(["--no-dotenv", "text", "--message", "Synthetic setup probe"]) == 0
'''
    env = {"PATH": os.environ.get("PATH", ""), "PYTHONPATH": str(ROOT),
           "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1"}
    result = subprocess.run([sys.executable, "-c", code], cwd=tmp_path, env=env,
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert '"clients_started": false' in result.stdout
    assert "offline fake" in result.stdout
    assert (sentinel.read_bytes(), sentinel.stat().st_mtime_ns) == before
    assert sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*")) == ["memories", "memories/graph.json"]


def test_doctor_redacts_config_and_does_not_claim_live_validation(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENROUTER_API_KEY", "fixture-secret")
    monkeypatch.setenv("SADAF_REASONING_PROVIDER", "openrouter")
    monkeypatch.setenv("SADAF_REASONING_MODEL", "fixture/model")
    assert main(["--no-dotenv", "doctor"]) == 0
    output = capsys.readouterr().out
    report = json.loads(output)
    assert report["configured_roles"]["reasoning"] == "openrouter"
    assert report["live_capabilities_verified"] is False
    assert "fixture-secret" not in output
    assert not list(tmp_path.iterdir())
    assert main(["--no-dotenv", "text", "--message", "Fixture"]) == 2


def test_doctor_invalid_configuration_returns_failure(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SADAF_M2_ENDPOINT", "https://secret:secret@fixture.invalid")
    assert main(["--no-dotenv", "doctor"]) == 2
    output = capsys.readouterr()
    assert "Configuration error" in output.err
    assert "secret" not in output.err


def test_text_cli_multiturn(tmp_path, monkeypatch, capsys):
    from io import StringIO

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "stdin", StringIO("Synthetic first\n\nSynthetic second\n"))
    assert main(["--no-dotenv", "text"]) == 0
    output = capsys.readouterr().out
    assert "turn 1" in output and "turn 2" in output
