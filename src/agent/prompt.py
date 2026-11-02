"""Assemble the completion prompt Hermes sends to the model provider."""

from __future__ import annotations

from skills.loader import Skill

INDEX_DESCRIPTION_CHARS = 200
SKILLS_HEADER = "## Skills"
REQUEST_HEADER = "## Request"
NO_SKILLS = "No skills are loaded."
SKILLS_PREAMBLE = (
    "Before answering, scan this skill index. Follow a skill if it is relevant. "
    "Ignore it if it is not."
)


def assemble_completion_prompt(
    prompt: str,
    skills: list[Skill],
    suggestion: str | None = None,
    context: str | None = None,
) -> str:
    """Return one prompt: a skill index, optional advisory and context blocks, then the request."""
    skills_block = _skills_block(skills)
    advisory = f"\n\n{suggestion}" if suggestion else ""
    retrieved = f"\n\n{context}" if context else ""
    return f"{skills_block}{advisory}{retrieved}\n\n{REQUEST_HEADER}\n{prompt}"


def _skills_block(skills: list[Skill]) -> str:
    if not skills:
        return f"{SKILLS_HEADER}\n{NO_SKILLS}"
    lines = "\n".join(_index_line(skill) for skill in skills)
    return f"{SKILLS_HEADER}\n{SKILLS_PREAMBLE}\n\n{lines}"


def _index_line(skill: Skill) -> str:
    return f"- {skill.name} ({skill.version}): {index_description(skill.body)}"


def index_description(body: str) -> str:
    text = " ".join(_purpose_paragraph(body).split())
    if len(text) <= INDEX_DESCRIPTION_CHARS:
        return text
    return text[: INDEX_DESCRIPTION_CHARS - 3].rstrip() + "..."


def _purpose_paragraph(body: str) -> str:
    paragraph: list[str] = []
    capture = False
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            if capture:
                break
            capture = stripped.lower() == "# purpose"
            continue
        if not capture:
            continue
        if not stripped:
            if paragraph:
                break
            continue
        paragraph.append(stripped)
    if paragraph:
        return " ".join(paragraph)
    for line in body.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and not stripped.startswith("---"):
            return stripped
    return ""
