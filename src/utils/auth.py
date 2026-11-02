"""Constant-time bearer comparison for Hermes HTTP surfaces."""

from __future__ import annotations

import secrets


def is_authorized(header: str | None, token: str) -> bool:
    """Return True when header is exactly Bearer plus the configured token."""
    expected = f"Bearer {token}"
    if header is None or len(header) != len(expected):
        return False
    return secrets.compare_digest(header, expected)
