"""Frozen retrieval eval on hash vectors. Provider embedders are measured with scripts/eval_retrieval.py."""

import json
from pathlib import Path

import pytest

import agent.core as core
from agent.core import HermesAgent
from chroma_fake import FakeChroma
from utils.settings import load_settings

# Measured on the frozen set: vector order alone scores 0.50 / 0.75.
HIT_AT_1_FLOOR = 0.66
HIT_AT_5_FLOOR = 0.83


def _rates(agent: HermesAgent, questions: list[dict[str, str]]) -> tuple[float, float]:
    first = within = 0
    for item in questions:
        ranked = [match["source_id"] for match in agent.search_documents(item["q"], 5)["matches"]]
        first += ranked[:1] == [item["expect"]]
        within += item["expect"] in ranked
    return first / len(questions), within / len(questions)


@pytest.fixture
def loaded(tmp_path: Path, repo_root: Path) -> tuple[HermesAgent, list[dict[str, str]]]:
    data = repo_root / "tests" / "test_data" / "retrieval"
    corpus = json.loads((data / "corpus.json").read_text(encoding="utf-8"))
    questions = json.loads((data / "questions.json").read_text(encoding="utf-8"))
    settings = load_settings(
        {
            "HERMES_ENV": "test",
            "CHROMA_HOST": "chromadb",
            "HERMES_MEMORY_DIR": str(tmp_path / "memory"),
            "HERMES_SKILLS_DIR": str(tmp_path / "skills"),
        }
    )
    agent = HermesAgent(settings, chroma_client=FakeChroma())
    for doc in corpus:
        agent.save_document(doc["id"], doc["text"], doc["source"])
    return agent, questions


def test_hash_retrieval_with_fusion_meets_the_floor(loaded) -> None:  # noqa: ANN001
    agent, questions = loaded
    hit_1, hit_5 = _rates(agent, questions)
    assert hit_1 >= HIT_AT_1_FLOOR
    assert hit_5 >= HIT_AT_5_FLOOR


def test_fusion_beats_vector_order_alone(loaded, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: ANN001
    agent, questions = loaded
    fused = _rates(agent, questions)
    monkeypatch.setattr(core, "fuse", lambda query, matches: list(matches))
    plain = _rates(agent, questions)
    assert fused[0] > plain[0]
    assert fused[1] >= plain[1]
