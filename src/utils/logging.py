"""Process logging for Hermes services."""

from __future__ import annotations

import logging


def configure_logging(level: str) -> logging.Logger:
    """Configure the hermes logger once and return it."""
    logger = logging.getLogger("hermes")
    resolved = getattr(logging, level.upper(), logging.INFO)
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=resolved,
            format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        )
    logger.setLevel(resolved)
    return logger
