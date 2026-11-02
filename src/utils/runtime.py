"""Startup check for an agent container with every Linux capability dropped."""

from __future__ import annotations

from pathlib import Path

from utils.settings import Settings, SettingsError

UNPRIVILEGED_PORT = 1024


def check_runtime(settings: Settings) -> None:
    """Confirm the process can serve after capabilities are dropped.

    Ports below 1024 need CAP_NET_BIND_SERVICE. Memory must be writable before
    the process accepts traffic.
    """
    if settings.hermes_port < UNPRIVILEGED_PORT:
        raise SettingsError(
            "HERMES_PORT must be 1024 or higher so the process can bind with all capabilities dropped"
        )
    memory = Path(settings.memory_dir)
    skills = Path(settings.skills_dir)
    try:
        memory.mkdir(parents=True, exist_ok=True)
        probe = memory / ".runtime-check"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        raise SettingsError("Memory directory is not writable") from exc
    if not skills.is_dir():
        raise SettingsError("Skills directory is not available")
