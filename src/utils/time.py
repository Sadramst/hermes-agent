"""Timezone parsing and current-time formatting without external dependencies."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_OFFSET_PATTERN = re.compile(r"^(?:UTC|GMT)?([+-])(\d{1,2})(?::?(\d{2}))?$", re.IGNORECASE)
_IANA_PATTERN = re.compile(r"^[A-Za-z_]+(?:/[A-Za-z0-9_+-]+)+$")

# Fallback fixed offsets for environments (such as minimal Windows venvs) lacking tzdata.
_COMMON_IANA_OFFSETS: dict[str, int] = {
    "Asia/Singapore": 8 * 60,
    "Asia/Kuala_Lumpur": 8 * 60,
    "Asia/Shanghai": 8 * 60,
    "Asia/Hong_Kong": 8 * 60,
    "Asia/Taipei": 8 * 60,
    "Australia/Perth": 8 * 60,
    "Asia/Tokyo": 9 * 60,
    "Asia/Dubai": 4 * 60,
    "Asia/Tehran": 3 * 60 + 30,
    "Europe/London": 0,
}


def check_timezone(raw: str) -> str:
    """Validate HERMES_TIMEZONE and return the normalized string."""
    value = raw.strip() or "UTC"
    if value.upper() in {"UTC", "GMT"}:
        return value.upper()
    if _parse_offset(value) is not None:
        return value
    if _IANA_PATTERN.fullmatch(value):
        return value
    raise ValueError(f"Invalid HERMES_TIMEZONE: {raw}")


def resolve_timezone(name: str) -> tuple[tzinfo, str]:
    """Return a tzinfo and effective label for a validated timezone string."""
    checked = check_timezone(name)
    if checked in {"UTC", "GMT"}:
        return timezone.utc, checked
    offset = _parse_offset(checked)
    if offset is not None:
        return offset, checked
    try:
        return ZoneInfo(checked), checked
    except ZoneInfoNotFoundError:
        minutes = _COMMON_IANA_OFFSETS.get(checked)
        if minutes is not None:
            return timezone(timedelta(minutes=minutes), name=checked), checked
        return timezone.utc, "UTC"


def now_report(timezone_name: str = "UTC", *, now_utc: datetime | None = None) -> dict[str, str]:
    """Return current UTC and configured local timestamps for personal assistant planning."""
    utc_dt = now_utc.astimezone(timezone.utc) if now_utc is not None else datetime.now(timezone.utc)
    tz, effective = resolve_timezone(timezone_name)
    local_dt = utc_dt.astimezone(tz)
    return {
        "timezone": effective,
        "requested_timezone": timezone_name,
        "local_iso": local_dt.isoformat(timespec="seconds"),
        "utc_iso": utc_dt.isoformat(timespec="seconds"),
        "date": local_dt.strftime("%Y-%m-%d"),
        "weekday": local_dt.strftime("%A"),
        "iso_week": local_dt.strftime("%G-W%V"),
    }


def _parse_offset(value: str) -> timezone | None:
    match = _OFFSET_PATTERN.fullmatch(value.strip())
    if match is None:
        return None
    sign = 1 if match.group(1) == "+" else -1
    hours = int(match.group(2))
    minutes = int(match.group(3) or "0")
    if hours > 23 or minutes > 59:
        return None
    delta = timedelta(hours=hours, minutes=minutes) * sign
    label = f"UTC{match.group(1)}{hours:02d}:{minutes:02d}"
    return timezone(delta, name=label)

