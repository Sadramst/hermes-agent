"""Reorder vector neighbors with a keyword ranking (reciprocal rank fusion)."""

from __future__ import annotations

import re

# Standard RRF damping constant. Larger values flatten the gap between neighboring ranks.
RRF_K = 60
_TOKEN = re.compile(r"[a-z0-9][a-z0-9._-]*[a-z0-9]|[a-z0-9]")
_STOPWORDS = frozenset(
    "a an and are as at be by do does for from how i in is it of on or the to was what when where "
    "which who why with you".split()
)


def fuse(query: str, matches: list[dict[str, object]]) -> list[dict[str, object]]:
    """Return matches ordered by vector rank plus keyword-overlap rank. Ties keep vector order."""
    terms = _terms(query)
    if len(matches) < 2 or not terms:
        return list(matches)
    overlaps = [len(terms & _terms(_text(match))) for match in matches]
    keyword_order = sorted(range(len(matches)), key=lambda index: (-overlaps[index], index))
    keyword_rank = {index: rank for rank, index in enumerate(keyword_order)}

    def score(index: int) -> float:
        lexical = 1 / (RRF_K + keyword_rank[index] + 1) if overlaps[index] else 0.0
        return 1 / (RRF_K + index + 1) + lexical

    order = sorted(range(len(matches)), key=lambda index: (-score(index), index))
    return [matches[index] for index in order]


def _terms(text: str) -> set[str]:
    return {token for token in _TOKEN.findall(text.lower()) if token not in _STOPWORDS}


def _text(match: dict[str, object]) -> str:
    text = match.get("text")
    return text if isinstance(text, str) else ""
