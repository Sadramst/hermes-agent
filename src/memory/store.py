"""Persist short memory records inside the configured memory directory."""

from __future__ import annotations

import re
from pathlib import Path

KEY_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")


class MemoryStore:
    """Write and read one file per memory key under a single root directory."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def check(self, key: str) -> None:
        """Reject a key that cannot be stored. This does not create a file."""
        self._path_for(key)

    def write(self, key: str, value: str) -> Path:
        path = self._path_for(key)
        path.write_text(value, encoding="utf-8")
        return path

    def read(self, key: str) -> str:
        return self._path_for(key).read_text(encoding="utf-8")

    def keys(self) -> list[str]:
        """Stored keys in name order. Files whose name is not a valid key are ignored."""
        return sorted(
            path.name
            for path in self.root.iterdir()
            if path.is_file() and KEY_PATTERN.fullmatch(path.name)
        )

    def _path_for(self, key: str) -> Path:
        if not KEY_PATTERN.fullmatch(key):
            raise ValueError(f"Invalid memory key: {key}")
        path = (self.root / key).resolve()
        if path.parent != self.root:
            raise ValueError(f"Memory key escapes storage directory: {key}")
        return path
