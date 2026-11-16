"""Personal assistant profile loader (SOUL.md and USER.md) for autonomous runs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from utils.time import now_report

MAX_PROFILE_DOC_CHARS = 3_000


@dataclass(frozen=True)
class PersonalProfile:
    """Loaded personal identity and user profile documents when configured."""

    soul: str
    user: str

    @property
    def loaded(self) -> bool:
        return bool(self.soul or self.user)


def load_personal_profile(profile_dir: str | Path | None) -> PersonalProfile:
    """Read SOUL.md and USER.md from `profile_dir` if present. Missing files stay empty."""
    if not profile_dir:
        return PersonalProfile(soul="", user="")
    root = Path(profile_dir)
    if not root.is_dir():
        return PersonalProfile(soul="", user="")
    return PersonalProfile(
        soul=_read_excerpt(root / "SOUL.md"),
        user=_read_excerpt(root / "USER.md"),
    )


def build_agent_system_prompt(
    profile: PersonalProfile,
    *,
    timezone_name: str = "UTC",
    provider_auth_mode: str = "api_key",
) -> str:
    """Build the system prompt injected into HermesAgent.run_agent() conversations."""
    clock = now_report(timezone_name)
    sections = [
        (
            "You are Hermes, Sadra's permanent personal assistant across software engineering, "
            "DevOps/VPS operations, personal development, personal financial advisory, and life admin."
        ),
        (
            f"Current time: {clock['local_iso']} ({clock['weekday']}, {clock['iso_week']}, "
            f"tz={clock['timezone']}, auth_mode={provider_auth_mode})."
        ),
        (
            "Operating rules:\n"
            "- Check `search_memory`, `list_memories`, `recall`, `search_documents`, or `read_skill` "
            "before guessing prior facts or procedures.\n"
            "- Persist durable facts using `remember` (dotted keys: profile.*, work.*, dev.*, "
            "goal.*, habit.*, finance.*, ops.*) or `save_document` for multi-paragraph notes.\n"
            "- Cite `[label]` whenever using passages from `search_documents`.\n"
            "- Financial advisory is strictly analytical and non-custodial: state assumptions, "
            "downside risks, and liquidity impacts; never execute trades/transfers or store raw credentials.\n"
            "- Stop and defer to human confirmation when any tool returns `ask_person`."
        ),
    ]
    if profile.soul:
        sections.append(f"## Identity (SOUL.md)\n{profile.soul}")
    if profile.user:
        sections.append(f"## User Profile (USER.md)\n{profile.user}")
    return "\n\n".join(sections)


def _read_excerpt(path: Path) -> str:
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8").strip()
    if len(text) <= MAX_PROFILE_DOC_CHARS:
        return text
    return text[: MAX_PROFILE_DOC_CHARS - 3].rstrip() + "..."

