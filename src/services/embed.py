"""Stable token-hash embeddings for the one Hermes document collection.

The vectors are deterministic and need no model download. Overlapping words
land closer together. This is keyword overlap, not a neural embedding.
"""

from __future__ import annotations

import hashlib
import math
import re

DIMENSION = 64
_TOKEN = re.compile(r"[a-z0-9]+")


def embed(text: str) -> list[float]:
    """Return a unit vector of length DIMENSION for text."""
    vector = [0.0] * DIMENSION
    tokens = _TOKEN.findall(text.lower())
    if not tokens:
        vector[0] = 1.0
        return vector
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        bucket = int.from_bytes(digest[:4], "big") % DIMENSION
        vector[bucket] += 1.0
    norm = math.sqrt(sum(value * value for value in vector))
    return [value / norm for value in vector]
