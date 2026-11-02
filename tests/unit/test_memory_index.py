"""Memory search index, citation-shaped search output, migration, and health."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent.core import HermesAgent, MemoryIndexOff
from api.app import create_app
from api.mcp_tools import NO_MEMORY_MATCHES, call_tool
from chroma_fake import FakeChroma
from services.chroma import ChromaError
from services.embed import embed
from utils.settings import load_settings


def _settings(tmp_path: Path, **extra: str):
    values = {
        "HERMES_ENV": "test",
        "CHROMA_HOST": "chromadb",
        "HERMES_MEMORY_DIR": str(tmp_path / "memory"),
        "HERMES_SKILLS_DIR": str(tmp_path / "skills"),
    }
    values.update(extra)
    return load_settings(values)


def _indexed(tmp_path: Path) -> tuple[HermesAgent, FakeChroma]:
    documents = FakeChroma()
    agent = HermesAgent(_settings(tmp_path, HERMES_MEMORY_INDEX="on"), chroma_client=documents)
    return agent, documents.bound_to("hermes-memory", None)


def test_remember_indexes_the_record_and_search_finds_it_by_meaning(tmp_path: Path) -> None:
    agent, memory = _indexed(tmp_path)
    assert agent.remember("office-wifi-hint", "The office wifi password hint is the street name.")
    agent.remember("lunch", "Lunch orders close at noon on Fridays.")
    assert "office-wifi-hint::0000" in memory.rows
    found = agent.search_memory("wifi password hint")
    assert found["collection"] == "hermes-memory"
    assert found["matches"][0]["key"] == "office-wifi-hint"


def test_overwriting_a_key_replaces_its_index_rows(tmp_path: Path) -> None:
    agent, memory = _indexed(tmp_path)
    agent.remember("note", "first version " * 300)
    agent.remember("note", "short second version")
    assert list(memory.rows) == ["note::0000"]


def test_memory_search_is_off_by_default(tmp_path: Path) -> None:
    agent = HermesAgent(_settings(tmp_path), chroma_client=FakeChroma())
    assert agent.memory_chroma is None
    with pytest.raises(MemoryIndexOff):
        agent.search_memory("anything")
    assert call_tool(agent, "search_memory", {"q": "anything"}) == "Memory search is off"


def test_an_index_failure_still_keeps_the_file(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    class _Down(FakeChroma):
        def upsert_chunks(self, *args: object) -> None:
            raise ChromaError("down", 503)

    agent = HermesAgent(
        _settings(tmp_path, HERMES_MEMORY_INDEX="on"),
        chroma_client=FakeChroma(),
        memory_chroma=_Down("hermes-memory"),
    )
    with caplog.at_level("WARNING", logger="hermes"):
        assert agent.remember("note", "durable fact") is True
    assert agent.recall("note") == "durable fact"
    assert "memory.index_failed key=note status=503" in caplog.text
    assert "durable fact" not in caplog.text


def test_reindex_memory_indexes_existing_files(tmp_path: Path) -> None:
    plain = HermesAgent(_settings(tmp_path), chroma_client=FakeChroma())
    plain.remember("alpha", "first fact")
    plain.remember("beta", "second fact")
    agent, memory = _indexed(tmp_path)
    assert agent.reindex_memory() == {"indexed": 2}
    assert sorted(memory.rows) == ["alpha::0000", "beta::0000"]
    assert agent.reindex_memory() == {"indexed": 2}
    assert memory.upserts == 2


def test_mcp_search_output_carries_citation_labels(tmp_path: Path) -> None:
    agent, _ = _indexed(tmp_path)
    agent.save_document("restore", "Restore the stack with deploy.sh prod.", "docs/deployment/ubuntu-server.md")
    agent.remember("office-wifi-hint", "The wifi hint is the street name.")
    documents = call_tool(agent, "search_documents", {"q": "restore the stack"})
    assert documents.startswith("[restore::0000] doc=restore source=docs/deployment/ubuntu-server.md\n")
    memory = call_tool(agent, "search_memory", {"q": "wifi hint", "limit": 1})
    assert memory == "key=office-wifi-hint\nThe wifi hint is the street name."
    assert call_tool(agent, "search_memory", {"q": "x", "extra": 1}) != NO_MEMORY_MATCHES


def test_memory_search_http_route(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            _settings(tmp_path, HERMES_MEMORY_INDEX="on"),
            chroma_reachable=lambda: True,
            chroma_client=FakeChroma(),
        )
    )
    off = TestClient(create_app(_settings(tmp_path / "off"), chroma_reachable=lambda: True, chroma_client=FakeChroma()))
    assert off.get("/memory/search", params={"q": "x"}).status_code == 400
    assert client.get("/memory/search", params={"q": "x"}).json()["matches"] == []


def test_migrate_copies_legacy_and_chunked_rows_into_the_active_collection(tmp_path: Path) -> None:
    server: dict[str, FakeChroma] = {}
    old = FakeChroma("hermes-documents", server)
    old.put_legacy("note-1", "tuesday meeting notes", embed("tuesday meeting notes"))
    old.put_legacy("bad id", "skipped", embed("skipped"))
    long_text = " ".join(f"Line {index} of the restore runbook." for index in range(150))
    writer = HermesAgent(_settings(tmp_path / "old"), chroma_client=old)
    writer.save_document("runbook", long_text, "runbook.md")

    active = FakeChroma("hermes-documents-v2", server)
    agent = HermesAgent(_settings(tmp_path, HERMES_DOCUMENTS_COLLECTION="hermes-documents-v2"), chroma_client=active)
    assert agent.migrate_documents("hermes-documents") == {"migrated": 2, "skipped": 1}
    assert active.rows["note-1::0000"][0] == "tuesday meeting notes"
    chunks = sorted((meta["chunk"], text) for text, _, meta in active.rows.values() if meta["doc_id"] == "runbook")
    assert active.rows["runbook::0000"][2]["source"] == "runbook.md"
    assert len(chunks) > 1
    with pytest.raises(ValueError, match="active collection"):
        agent.migrate_documents("hermes-documents-v2")


def test_health_reports_retrieval_without_secrets(tmp_path: Path) -> None:
    key = "0123456789abcdef"
    settings = _settings(
        tmp_path,
        HERMES_EMBED_BASE_URL="https://embed.example/v1",
        HERMES_EMBED_MODEL="text-embed-1",
        HERMES_EMBED_API_KEY=key,
        HERMES_RAG_MODE="shadow",
    )
    client = TestClient(create_app(settings, chroma_reachable=lambda: True, chroma_client=FakeChroma()))
    response = client.get("/health")
    assert response.json()["retrieval"] == {
        "rag_mode": "shadow",
        "embedder": "text-embed-1",
        "documents_collection": "hermes-documents-v2",
        "memory_index": False,
        "memory_collection": "hermes-memory-v2",
    }
    assert key not in response.text
