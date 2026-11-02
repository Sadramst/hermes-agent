"""Memory writes stay inside the configured directory."""

import pytest

from memory.store import MemoryStore


def test_write_and_read_round_trip(tmp_path) -> None:
    store = MemoryStore(tmp_path)
    store.write("boot", "started")
    assert store.read("boot") == "started"
    assert (tmp_path / "boot").is_file()


def test_path_escape_is_rejected(tmp_path) -> None:
    store = MemoryStore(tmp_path)
    with pytest.raises(ValueError, match="Invalid memory key"):
        store.write("../escape", "nope")
    assert not (tmp_path.parent / "escape").exists()
