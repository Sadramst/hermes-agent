"""Startup check used before serving with capabilities dropped."""

from pathlib import Path

import pytest

from api.server import serve
from utils.runtime import check_runtime
from utils.settings import Settings, SettingsError, load_settings


def _settings(tmp_path: Path, port: str = "8080") -> Settings:
    skills = tmp_path / "skills"
    skills.mkdir()
    return load_settings(
        {
            "HERMES_ENV": "dev",
            "CHROMA_HOST": "localhost",
            "HERMES_PORT": port,
            "HERMES_MEMORY_DIR": str(tmp_path / "memory"),
            "HERMES_SKILLS_DIR": str(skills),
        }
    )


def test_runtime_check_accepts_an_unprivileged_port_and_writable_memory(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    check_runtime(settings)
    assert not (tmp_path / "memory" / ".runtime-check").exists()


def test_runtime_check_rejects_a_privileged_port(tmp_path: Path) -> None:
    settings = _settings(tmp_path, port="80")
    with pytest.raises(SettingsError, match="HERMES_PORT"):
        check_runtime(settings)


def test_serve_stops_when_the_skills_directory_is_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HERMES_ENV", "dev")
    monkeypatch.setenv("CHROMA_HOST", "localhost")
    monkeypatch.setenv("HERMES_PORT", "8080")
    monkeypatch.setenv("HERMES_MEMORY_DIR", str(tmp_path / "memory"))
    monkeypatch.setenv("HERMES_SKILLS_DIR", str(tmp_path / "missing-skills"))
    with pytest.raises(SettingsError, match="Skills directory"):
        serve()
