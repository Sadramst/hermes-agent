"""Skill loader and the bootstrap skill document."""

from pathlib import Path

import pytest

from skills.loader import SkillLoader

REQUIRED_HEADINGS = (
    "Purpose",
    "Inputs",
    "Outputs",
    "Execution flow",
    "Error handling",
    "Logging",
    "Versioning",
    "Test coverage",
    "Documentation references",
)


def test_loader_reads_skill_documents(tmp_path: Path) -> None:
    skill_dir = tmp_path / "demo"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: demo\nversion: 0.1.0\n---\n# Purpose\nDemo\n",
        encoding="utf-8",
    )
    skills = SkillLoader(tmp_path).load()
    assert [(skill.name, skill.version) for skill in skills] == [("demo", "0.1.0")]


def test_missing_directory_returns_no_skills(tmp_path: Path) -> None:
    assert SkillLoader(tmp_path / "absent").load() == []


def test_unclosed_front_matter_raises(tmp_path: Path) -> None:
    skill_dir = tmp_path / "bad"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: bad\n", encoding="utf-8")
    with pytest.raises(ValueError, match="front matter"):
        SkillLoader(tmp_path).load()


def test_bootstrap_skill_is_present(repo_root: Path) -> None:
    skills = SkillLoader(repo_root / "storage" / "skills").load()
    bootstrap = next(skill for skill in skills if skill.name == "bootstrap-hermes-stack")
    assert bootstrap.version == "1.19.0"
    for heading in REQUIRED_HEADINGS:
        assert f"# {heading}" in bootstrap.body
