"""Load Hermes skills stored as SKILL.md documents."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("hermes.skills")


@dataclass(frozen=True)
class Skill:
    name: str
    version: str
    path: Path
    body: str


class SkillLoader:
    """Read `*/SKILL.md` files from the skills root."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()

    def load(self) -> list[Skill]:
        if not self.root.exists():
            logger.info("Skills directory is absent: %s", self.root)
            return []
        skills: list[Skill] = []
        for skill_file in sorted(self.root.glob("*/SKILL.md")):
            try:
                skills.append(self._parse(skill_file))
            except ValueError:
                logger.exception("Failed to load skill at %s", skill_file)
                raise
        return skills

    def _parse(self, path: Path) -> Skill:
        text = path.read_text(encoding="utf-8")
        meta, body = _split_front_matter(text, path)
        name = meta.get("name") or path.parent.name
        version = meta.get("version") or "0.0.0"
        return Skill(name=name, version=version, path=path, body=body)


def _split_front_matter(text: str, path: Path) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        raise ValueError(f"Unclosed front matter in {path}")
    meta: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if not line.strip():
            continue
        if ":" not in line:
            raise ValueError(f"Invalid front matter in {path}")
        key, value = line.split(":", 1)
        meta[key.strip()] = value.strip()
    return meta, text[end + 5 :]
