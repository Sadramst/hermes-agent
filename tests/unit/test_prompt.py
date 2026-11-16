"""Completion prompt assembly keeps the skill index in a stable wrapper."""

from pathlib import Path

from agent.prompt import (
    INDEX_DESCRIPTION_CHARS,
    NO_SKILLS,
    REQUEST_HEADER,
    SKILLS_HEADER,
    SKILLS_PREAMBLE,
    assemble_completion_prompt,
)
from skills.loader import Skill, SkillLoader


def _skill(name: str, version: str, body: str) -> Skill:
    return Skill(name=name, version=version, path=Path(name) / "SKILL.md", body=body)


def test_context_block_sits_between_the_index_and_the_request() -> None:
    skill = _skill("demo", "0.1.0", "# Purpose\n\nDemo skill for routing.\n")
    context = "## Context\n<passage label=\"doc::0000\">\nDetails\n</passage>"
    prompt = assemble_completion_prompt("status", [skill], context)
    assert "- demo (0.1.0): Demo skill for routing." in prompt
    assert prompt.index(context) < prompt.index(REQUEST_HEADER)
    assert prompt.endswith(f"{REQUEST_HEADER}\nstatus")


def test_empty_skills_keep_a_stable_wrapper() -> None:
    prompt = assemble_completion_prompt("status", [])
    assert prompt.startswith(f"{SKILLS_HEADER}\n{NO_SKILLS}")
    assert prompt.endswith(f"{REQUEST_HEADER}\nstatus")
    assert "demo" not in prompt


def test_skill_index_includes_name_version_and_purpose() -> None:
    skill = _skill(
        "demo",
        "0.1.0",
        "# Purpose\n\nDemo skill for routing.\n\n# Inputs\n\nNone.\n",
    )
    prompt = assemble_completion_prompt("status", [skill])
    assert SKILLS_PREAMBLE in prompt
    assert "- demo (0.1.0): Demo skill for routing." in prompt
    assert prompt.endswith(f"{REQUEST_HEADER}\nstatus")
    assert "# Inputs" not in prompt


def test_purpose_description_is_truncated() -> None:
    purpose = "word " * 80
    skill = _skill("long", "1.0.0", f"# Purpose\n{purpose}\n")
    prompt = assemble_completion_prompt("go", [skill])
    line = next(item for item in prompt.splitlines() if item.startswith("- long "))
    description = line.split(": ", 1)[1]
    assert len(description) == INDEX_DESCRIPTION_CHARS
    assert description.endswith("...")


def test_body_without_purpose_uses_the_first_text_line() -> None:
    skill = _skill("plain", "0.0.1", "Just a note.\nMore text.\n")
    prompt = assemble_completion_prompt("ask", [skill])
    assert "- plain (0.0.1): Just a note." in prompt


def test_bootstrap_skill_purpose_lands_in_the_index(repo_root: Path) -> None:
    skills = SkillLoader(repo_root / "storage" / "skills").load()
    prompt = assemble_completion_prompt("status", skills)
    assert "bootstrap-hermes-stack (1.19.0): Bring up the Hermes Agent service" in prompt
