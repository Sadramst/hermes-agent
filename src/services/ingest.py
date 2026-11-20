"""Directory ingestion for indexing a personal Brain vault or project docs into ChromaDB."""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

from services.documents import MAX_SOURCE_CHARS, MAX_TEXT_CHARS
from services.workspace import IGNORED_DIRS, is_secret_path

DOC_EXTENSIONS: frozenset[str] = frozenset(
    {".md", ".markdown", ".txt", ".rst", ".yaml", ".yml", ".toml", ".json"}
)
CODE_EXTENSIONS: frozenset[str] = frozenset(
    {".py", ".ts", ".tsx", ".js", ".jsx", ".sh", ".ps1", ".sql", ".go", ".rs", ".java", ".html", ".css"}
)
MAX_INGEST_FILES = 500
_SLUG_INVALID = re.compile(r"[^A-Za-z0-9._-]+")


def stable_doc_id(prefix: str, rel_posix: str) -> str:
    """Build a valid, collision-free document ID (<= 96 chars) for a relative path."""
    cleaned_prefix = _SLUG_INVALID.sub("-", prefix.strip()).strip(".-") or "brain"
    slug = _SLUG_INVALID.sub("-", rel_posix).strip(".-") or "file"
    digest = hashlib.sha256(f"{cleaned_prefix}:{rel_posix}".encode("utf-8")).hexdigest()[:8]
    base = f"{cleaned_prefix}-{slug}"[:87].rstrip(".-")
    if not base or not base[0].isalnum():
        base = f"doc-{base}" if base else "doc"
    return f"{base}-{digest}"[:96]


def ingest_directory(
    agent: object,
    directory: str | Path,
    *,
    prefix: str = "brain",
    include_code: bool = False,
    max_files: int = 200,
) -> dict[str, object]:
    """Walk `directory` cleanly, skip ignored/secret files, and upsert changed docs to ChromaDB."""
    root = Path(directory).resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Ingestion directory not found: {directory}")

    capped = max(1, min(int(max_files), MAX_INGEST_FILES))
    allowed_exts = DOC_EXTENSIONS | CODE_EXTENSIONS if include_code else DOC_EXTENSIONS
    save_fn = getattr(agent, "save_document")

    ingested = 0
    unchanged = 0
    skipped = 0
    errors = 0
    total_seen = 0

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in IGNORED_DIRS)
        cur = Path(dirpath)
        for fname in sorted(filenames):
            full = cur / fname
            try:
                rel = full.resolve().relative_to(root)
            except ValueError:
                continue
            if is_secret_path(rel):
                continue
            if full.suffix.lower() not in allowed_exts:
                continue

            total_seen += 1
            if total_seen > capped:
                skipped += 1
                continue

            try:
                raw = full.read_bytes()
            except OSError:
                errors += 1
                continue
            if b"\x00" in raw[:8192]:
                skipped += 1
                continue
            text = raw.decode("utf-8", errors="replace")
            if not text.strip() or len(text) > MAX_TEXT_CHARS:
                skipped += 1
                continue

            rel_posix = rel.as_posix()
            doc_id = stable_doc_id(prefix, rel_posix)
            source_label = f"{prefix}:{rel_posix}"[:MAX_SOURCE_CHARS]
            try:
                outcome = save_fn(doc_id, text, source=source_label)
            except Exception:  # noqa: BLE001
                errors += 1
                continue
            if isinstance(outcome, dict) and outcome.get("unchanged"):
                unchanged += 1
            else:
                ingested += 1

    return {
        "root": root.name,
        "ingested": ingested,
        "unchanged": unchanged,
        "skipped": skipped,
        "errors": errors,
        "total_seen": total_seen,
    }
