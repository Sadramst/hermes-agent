"""CLI commands."""

import json
from pathlib import Path


def test_cli_lists_skills(tmp_path: Path, monkeypatch, capsys) -> None:
    from cli.main import main

    skill_dir = tmp_path / "skills" / "alpha"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: alpha\nversion: 1.2.3\n---\n# Purpose\nA\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HERMES_ENV", "dev")
    monkeypatch.setenv("CHROMA_HOST", "localhost")
    monkeypatch.setenv("HERMES_SKILLS_DIR", str(tmp_path / "skills"))
    monkeypatch.setenv("HERMES_MEMORY_DIR", str(tmp_path / "memory"))

    assert main(["skills"]) == 0
    assert "alpha 1.2.3" in capsys.readouterr().out


def test_cli_health_prints_json(tmp_path: Path, monkeypatch, capsys) -> None:
    from cli.main import main

    monkeypatch.setenv("HERMES_ENV", "test")
    monkeypatch.setenv("CHROMA_HOST", "127.0.0.1")
    monkeypatch.setenv("CHROMA_PORT", "9")
    monkeypatch.setenv("HERMES_SKILLS_DIR", str(tmp_path / "skills"))
    monkeypatch.setenv("HERMES_MEMORY_DIR", str(tmp_path / "memory"))

    assert main(["health"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["environment"] == "test"
    assert payload["chroma"]["reachable"] is False
