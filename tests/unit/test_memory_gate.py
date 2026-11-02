"""Memory write judgments stay in state. Soft mode skips one-shot chatter."""

import json

import pytest

from agent.core import HermesAgent
from agent.decisions.memory_gate import (
    EXCERPT_CHARS,
    KIND,
    KINDS,
    WORTH,
    WORTH_LABEL,
    judge,
    label_memory,
    record_memory,
)
from services.chroma import ChromaClient
from services.jev import JevError, JevResult
from utils.settings import load_settings


class _Jev:
    def __init__(self, responses: list[dict[str, object] | Exception]) -> None:
        self.responses = responses
        self.calls: list[tuple[object, dict[str, object]]] = []

    def evaluate(self, state: object, questions: dict[str, object]) -> JevResult:
        self.calls.append((state, questions))
        item = self.responses[len(self.calls) - 1]
        if isinstance(item, Exception):
            raise item
        return JevResult(model="jev-1.13.0", answers=item, usage={})


def _kept(kind: str = "fact", worth: float = 0.8) -> dict[str, object]:
    return {
        "worth": {"type": "noul", "noul": worth},
        "kind": {
            "type": "choice",
            "choice": kind,
            "probabilities": {kind: 0.8, "none": 0.2},
            "confidence": 0.7,
        },
    }


def _agent(tmp_path, mode: str, jev: object) -> HermesAgent:
    values = {
        "HERMES_ENV": "test",
        "CHROMA_HOST": "chromadb",
        "HERMES_MEMORY_DIR": str(tmp_path / f"memory-{mode}"),
        "HERMES_SKILLS_DIR": str(tmp_path / "skills"),
        "HERMES_JEV_MODE": mode,
    }
    if mode != "off":
        values["HERMES_JEV_API_KEY"] = "fedcba9876543210"
    return HermesAgent(
        load_settings(values),
        chroma_client=ChromaClient("chromadb", 8000, opener=lambda request, timeout: None),
        jev_client=jev,
    )


def test_one_request_keeps_the_value_out_of_the_questions() -> None:
    value = "value-secret-7c2e " + ("word " * 800)
    jev = _Jev([_kept()])
    result = judge(jev, "boot", value)
    assert result.kind == "fact"
    assert result.reason == "ok"
    state, questions = jev.calls[0]
    assert state["key"] == "boot"
    assert state["value"] == " ".join(value.split())[:EXCERPT_CHARS]
    dumped = json.dumps(questions)
    assert "value-secret-7c2e" not in dumped
    assert questions["worth"]["instructions"] == WORTH
    assert questions["kind"]["instructions"] == KIND
    assert questions["kind"]["criteria"]["none"]
    assert set(questions["kind"]["criteria"]) == {"none", *KINDS}


def test_worth_boundary_and_none_label_an_empty_kind() -> None:
    kept = _kept(worth=WORTH_LABEL)
    assert label_memory(kept) == ("fact", "ok")
    low = _kept(worth=WORTH_LABEL - 0.01)
    assert label_memory(low) == ("", "worth")
    chatter = _kept(kind="none", worth=0.9)
    assert label_memory(chatter) == ("", "none")
    unknown = _kept(kind="secret", worth=0.9)
    assert label_memory(unknown) == ("", "unknown")


def test_shadow_logs_the_kind_and_still_writes(tmp_path, caplog: pytest.LogCaptureFixture) -> None:
    value = "value-secret-7c2e"
    jev = _Jev([_kept()])
    agent = _agent(tmp_path, "shadow", jev)
    with caplog.at_level("INFO", logger="hermes.jev"):
        agent.remember("boot", value)
    assert agent.recall("boot") == value
    assert len(jev.calls) == 1
    assert "pack=memory-write" in caplog.text
    assert "kind=fact" in caplog.text
    assert "memory_key=boot" in caplog.text
    assert "persisted=true" in caplog.text
    assert "reason=ok" in caplog.text
    assert value not in caplog.text
    assert "fedcba9876543210" not in caplog.text


def test_mode_off_writes_without_calling_jev(tmp_path) -> None:
    jev = _Jev([_kept()])
    agent = _agent(tmp_path, "off", jev)
    agent.remember("boot", "started")
    assert agent.recall("boot") == "started"
    assert jev.calls == []


def test_soft_skips_chatter_and_keeps_a_durable_fact(
    tmp_path, caplog: pytest.LogCaptureFixture
) -> None:
    jev = _Jev([_kept(kind="none", worth=0.9), _kept(worth=WORTH_LABEL), _kept(worth=WORTH_LABEL - 0.01)])
    agent = _agent(tmp_path, "soft", jev)
    with caplog.at_level("INFO", logger="hermes.jev"):
        agent.remember("boot", "ping")
        agent.remember("fact", "keeps")
        agent.remember("weak", "maybe")
    with pytest.raises(FileNotFoundError):
        agent.recall("boot")
    assert agent.recall("fact") == "keeps"
    with pytest.raises(FileNotFoundError):
        agent.recall("weak")
    assert len(jev.calls) == 3
    assert "reason=none" in caplog.text
    assert "persisted=false" in caplog.text
    assert "effective=refuse" in caplog.text
    assert "reason=ok" in caplog.text
    assert "reason=worth" in caplog.text
    assert "ping" not in caplog.text.replace("looping", "")


def test_shadow_still_writes_chatter(tmp_path, caplog: pytest.LogCaptureFixture) -> None:
    jev = _Jev([_kept(kind="none", worth=0.1)])
    agent = _agent(tmp_path, "shadow", jev)
    with caplog.at_level("INFO", logger="hermes.jev"):
        agent.remember("boot", "ping")
    assert agent.recall("boot") == "ping"
    assert "persisted=true" in caplog.text
    assert "effective=advise" in caplog.text
    assert "proposed=refuse" in caplog.text


def test_soft_jev_error_still_writes(tmp_path, caplog: pytest.LogCaptureFixture) -> None:
    jev = _Jev([JevError("Jev request failed", 429)])
    agent = _agent(tmp_path, "soft", jev)
    with caplog.at_level("INFO", logger="hermes.jev"):
        agent.remember("boot", "started")
    assert agent.recall("boot") == "started"
    assert "reason=jev_error" in caplog.text
    assert "persisted=true" in caplog.text
    assert "effective=fallback_llm" in caplog.text


def test_jev_error_still_writes(tmp_path, caplog: pytest.LogCaptureFixture) -> None:
    jev = _Jev([JevError("Jev request failed", 429)])
    agent = _agent(tmp_path, "shadow", jev)
    with caplog.at_level("INFO", logger="hermes.jev"):
        agent.remember("boot", "started")
    assert agent.recall("boot") == "started"
    assert "reason=jev_error" in caplog.text
    assert "persisted=true" in caplog.text


def test_an_invalid_key_does_not_call_jev(tmp_path) -> None:
    jev = _Jev([_kept()])
    agent = _agent(tmp_path, "shadow", jev)
    with pytest.raises(ValueError):
        agent.remember("../secret", "nope")
    assert jev.calls == []


def test_record_omits_the_value(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level("INFO", logger="hermes.jev"):
        record = record_memory(
            mode="shadow",
            model="jev-1.13.0",
            memory_key="boot",
            kind="procedure",
            answers=_kept("procedure"),
            reason="ok",
            persisted=True,
        )
    assert record["comparison"]["persisted"] is True
    assert record["effective"] == "advise"
    assert "kind=procedure" in caplog.text
    assert "value-secret" not in caplog.text
