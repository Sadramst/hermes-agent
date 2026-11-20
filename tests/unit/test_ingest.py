"""Unit, HTTP, and CLI tests for Brain directory and project document ingestion."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent.core import HermesAgent
from api.app import create_app
from cli.main import main as cli_main
from services.chunking import content_hash
from services.ingest import stable_doc_id
from utils.settings import load_settings

TOKEN = "fedcba9876543210"


class _TrackingChroma:
    def __init__(self) -> None:
        self.docs: dict[str, dict[str, object]] = {}

    def heartbeat(self) -> bool:
        return True

    def source_metadatas(self, field: str, value: str) -> list[dict[str, object]]:
        row = self.docs.get(value)
        return [dict(row["metadata"])] if row else []  # type: ignore[arg-type]

    def delete_source(self, field: str, value: str) -> None:
        self.docs.pop(value, None)

    def upsert_chunks(self, ids: list[str], texts: list[str], embeddings: list, metadatas: list) -> None:
        doc_id = str(metadatas[0]["doc_id"])
        self.docs[doc_id] = {"text": texts[0], "metadata": metadatas[0]}


def test_stable_doc_id_is_valid_and_unique() -> None:
    id_a = stable_doc_id("brain", "notes/2026/architecture plan.md")
    id_b = stable_doc_id("brain", "notes/2026/architecture-plan.md")
    assert id_a != id_b
    assert len(id_a) <= 96
    assert id_a[0].isalnum()


def test_ingest_directory_skips_secrets_binary_and_deduplicates(tmp_path: Path) -> None:
    brain = tmp_path / "knowledge"
    (brain / "daily").mkdir(parents=True)
    (brain / ".git").mkdir()
    (brain / "daily" / "goals.md").write_text("# Weekly Goals\nShip v0.6.0 cleanly.\n", encoding="utf-8")
    (brain / "script.py").write_text("print('hi')\n", encoding="utf-8")
    (brain / ".env.prod").write_text("SECRET=123\n", encoding="utf-8")
    (brain / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (brain / "image.md").write_bytes(b"\x00binary")

    settings = load_settings(
        {
            "HERMES_ENV": "test",
            "CHROMA_HOST": "chromadb",
            "HERMES_MEMORY_DIR": str(tmp_path / "memory"),
            "HERMES_SKILLS_DIR": str(tmp_path / "skills"),
        }
    )
    chroma = _TrackingChroma()
    agent = HermesAgent(settings, chroma_client=chroma)  # type: ignore[arg-type]

    first = agent.ingest_directory(str(brain), prefix="brain")
    assert first == {
        "root": "knowledge",
        "ingested": 1,
        "unchanged": 0,
        "skipped": 1,
        "errors": 0,
        "total_seen": 2,
    }
    second = agent.ingest_directory(str(brain), prefix="brain")
    assert second["ingested"] == 0
    assert second["unchanged"] == 1

    with_code = agent.ingest_directory(str(brain), prefix="brain", include_code=True)
    assert with_code["ingested"] == 1
    assert with_code["unchanged"] == 1
    assert content_hash("print('hi')\n")


def test_http_ingest_and_cli_projects_and_ingest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    ws = tmp_path / "workspace"
    proj = ws / "demo"
    proj.mkdir(parents=True)
    (proj / "README.md").write_text("# Demo\nRun tests.\n", encoding="utf-8")
    (proj / "app.py").write_text("x = 1\n", encoding="utf-8")

    settings = load_settings(
        {
            "HERMES_ENV": "test",
            "CHROMA_HOST": "chromadb",
            "HERMES_API_TOKEN": TOKEN,
            "HERMES_MEMORY_DIR": str(tmp_path / "memory"),
            "HERMES_SKILLS_DIR": str(tmp_path / "skills"),
            "HERMES_PROJECTS_DIR": str(ws),
            "HERMES_WORKSPACE_MODE": "ro",
        }
    )
    client = TestClient(
        create_app(settings, chroma_reachable=lambda: True, chroma_client=_TrackingChroma())  # type: ignore[arg-type]
    )
    resp = client.post(
        "/projects/demo/ingest",
        json={"include_code": True},
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    assert resp.status_code == 200
    assert resp.json()["ingested"] == 2

    monkeypatch.setenv("HERMES_ENV", "test")
    monkeypatch.setenv("CHROMA_HOST", "chromadb")
    monkeypatch.setenv("HERMES_MEMORY_DIR", str(tmp_path / "memory"))
    monkeypatch.setenv("HERMES_SKILLS_DIR", str(tmp_path / "skills"))
    monkeypatch.setenv("HERMES_PROJECTS_DIR", str(ws))
    monkeypatch.setenv("HERMES_WORKSPACE_MODE", "ro")

    assert cli_main(["projects"]) == 0
    proj_payload = json.loads(capsys.readouterr().out)
    assert proj_payload["enabled"] is True
    assert proj_payload["projects"] == [{"name": "demo", "is_git": False, "has_readme": True}]

    assert cli_main(["ingest", str(tmp_path / "missing")]) == 1
    capsys.readouterr()
