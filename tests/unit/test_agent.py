"""Agent wiring keeps memory and skills inside their directories."""

import json
from pathlib import Path

import pytest

from agent.core import HermesAgent
from agent.decisions.guardrails import BLOCK_TEXT, REVIEW_TEXT
from agent.decisions.skill_suggestion import ADVISORY_NONE, FITS_QUESTION, WHICH, suggestion_block
from agent.prompt import NO_SKILLS, REQUEST_HEADER, assemble_completion_prompt
from services.chroma import ChromaClient
from services.jev import JevError, JevResult
from services.model import MAX_PROMPT_CHARS
from utils.settings import load_settings


class _Model:
    model = "hermes-model"

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def complete(self, prompt: str, *, model: str | None = None) -> str:
        self.prompts.append(prompt)
        return "ready"


class _Response:
    status = 200

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *args: object) -> bool:
        return False


def test_agent_uses_configured_directories(tmp_path: Path) -> None:
    skills_root = tmp_path / "skills"
    skill_dir = skills_root / "demo"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: demo\nversion: 0.1.0\n---\n# Purpose\nDemo\n",
        encoding="utf-8",
    )
    memory_root = tmp_path / "memory"
    settings = load_settings(
        {
            "HERMES_ENV": "test",
            "CHROMA_HOST": "chromadb",
            "HERMES_MEMORY_DIR": str(memory_root),
            "HERMES_SKILLS_DIR": str(skills_root),
        }
    )
    seen: list[str] = []

    def opener(request, timeout):  # noqa: ANN001
        seen.append(request.full_url)
        return _Response()

    agent = HermesAgent(settings, chroma_client=ChromaClient("chromadb", 8000, opener=opener))
    agent.remember("boot", "started")
    assert agent.recall("boot") == "started"
    assert (memory_root / "boot").read_text(encoding="utf-8") == "started"
    assert [skill.name for skill in agent.list_skills()] == ["demo"]
    report = agent.health()
    assert report["chroma"]["reachable"] is True
    assert seen[0] == "http://chromadb:8000/api/v2/heartbeat"
    for path in tmp_path.rglob("*"):
        if path.is_file():
            assert path.resolve().is_relative_to(tmp_path.resolve())


def _model_settings(tmp_path: Path, skills_dir: Path) -> object:
    return load_settings(
        {
            "HERMES_ENV": "test",
            "CHROMA_HOST": "chromadb",
            "HERMES_MEMORY_DIR": str(tmp_path / "memory"),
            "HERMES_SKILLS_DIR": str(skills_dir),
            "HERMES_MODEL_BASE_URL": "https://models.example/v1",
            "HERMES_MODEL_NAME": "hermes-model",
            "HERMES_MODEL_API_KEY": "0123456789abcdef",
        }
    )


def test_complete_sends_the_skill_index_and_the_request(tmp_path: Path) -> None:
    skills_root = tmp_path / "skills"
    skill_dir = skills_root / "demo"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: demo\nversion: 0.1.0\n---\n# Purpose\nDemo\n",
        encoding="utf-8",
    )
    model = _Model()
    agent = HermesAgent(
        _model_settings(tmp_path, skills_root),
        chroma_client=ChromaClient("chromadb", 8000, opener=lambda request, timeout: None),
        model_client=model,
    )
    result = agent.complete("status")
    assert result == {"text": "ready", "model": "hermes-model"}
    assert "- demo (0.1.0): Demo" in model.prompts[0]
    assert model.prompts[0].endswith(f"{REQUEST_HEADER}\nstatus")


def test_complete_with_no_skills_keeps_the_request(tmp_path: Path) -> None:
    skills_root = tmp_path / "empty-skills"
    model = _Model()
    agent = HermesAgent(
        _model_settings(tmp_path, skills_root),
        chroma_client=ChromaClient("chromadb", 8000, opener=lambda request, timeout: None),
        model_client=model,
    )
    agent.complete("status")
    assert NO_SKILLS in model.prompts[0]
    assert model.prompts[0].endswith(f"{REQUEST_HEADER}\nstatus")
    assert "demo" not in model.prompts[0]


class _Jev:
    def __init__(self, responses: list[dict[str, object] | Exception]) -> None:
        self.responses = responses
        self.calls: list[tuple[object, dict[str, object]]] = []

    def evaluate(self, state: object, questions: dict[str, object]) -> JevResult:
        self.calls.append((state, questions))
        if "looping" in questions:
            return JevResult(model="jev-1.13.0", answers=_supervisor_quiet(), usage={})
        scripted = [call for call in self.calls if "looping" not in call[1]]
        item = self.responses[len(scripted) - 1]
        if isinstance(item, Exception):
            raise item
        return JevResult(model="jev-1.13.0", answers=item, usage={})


def _write_skill(root: Path, name: str, purpose: str) -> None:
    skill_dir = root / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\nversion: 1.0.0\n---\n# Purpose\n{purpose}\n",
        encoding="utf-8",
    )


def _agent(tmp_path: Path, mode: str, skills: Path, model: _Model, jev: object) -> HermesAgent:
    values = {
        "HERMES_ENV": "test",
        "CHROMA_HOST": "chromadb",
        "HERMES_MEMORY_DIR": str(tmp_path / f"memory-{mode}"),
        "HERMES_SKILLS_DIR": str(skills),
        "HERMES_MODEL_BASE_URL": "https://models.example/v1",
        "HERMES_MODEL_NAME": "hermes-model",
        "HERMES_MODEL_API_KEY": "0123456789abcdef",
        "HERMES_JEV_MODE": mode,
    }
    if mode != "off":
        values["HERMES_JEV_API_KEY"] = "fedcba9876543210"
    return HermesAgent(
        _model_settings_with(values),
        chroma_client=ChromaClient("chromadb", 8000, opener=lambda request, timeout: None),
        model_client=model,
        jev_client=jev,
    )


def _wide(choice: str, probabilities: dict[str, float], noul: float, prose: float) -> dict[str, object]:
    return {
        "which": {
            "type": "choice",
            "choice": choice,
            "probabilities": probabilities,
            "confidence": 0.8,
        },
        "gate::acts_on_user_system": {"type": "noul", "noul": noul},
        "gate::would_follow_documented_procedure": {"type": "noul", "noul": noul},
        "gate::prose_suffices": {"type": "noul", "noul": prose},
    }


def _rerank_beta() -> dict[str, object]:
    return {
        "which": {
            "type": "choice",
            "choice": "beta",
            "probabilities": {"beta": 0.6, "alpha": 0.3, "none": 0.1},
            "confidence": 0.8,
        },
        "fits::alpha": {"type": "noul", "noul": 0.2},
        "fits::beta": {"type": "noul", "noul": 0.8},
    }


def _guard_pass() -> dict[str, object]:
    return {
        "jailbreak": {"type": "noul", "noul": 0.01},
        "credential_harvest": {"type": "noul", "noul": 0.01},
        "self_harm": {"type": "noul", "noul": 0.01},
        "blast_radius": {"type": "score", "score": 0.1},
    }


def _guard_block() -> dict[str, object]:
    screened = _guard_pass()
    screened["blast_radius"] = {"type": "score", "score": 3.0}
    return screened


def _supervisor_quiet() -> dict[str, object]:
    return {
        "looping": {"type": "noul", "noul": 0.01},
        "progress": {"type": "score", "score": 1.0},
        "complete": {"type": "noul", "noul": 0.01},
    }


def _router_frontier() -> dict[str, object]:
    return {
        "tier": {
            "type": "choice",
            "choice": "frontier",
            "probabilities": {"frontier": 0.8, "small": 0.1, "none": 0.1},
            "confidence": 0.8,
        }
    }


def _with_guards(*responses: dict[str, object] | Exception) -> list[dict[str, object] | Exception]:
    return [*responses, _guard_pass(), _router_frontier(), _guard_pass(), _supervisor_quiet()]


def test_complete_skips_jev_when_mode_is_off(tmp_path: Path) -> None:
    prompt = "caller-secret-7c2e"
    skills = tmp_path / "skills-off"
    _write_skill(skills, "alpha", "Alpha skill")
    jev = _Jev([_wide("alpha", {"alpha": 0.9, "none": 0.1}, 0.9, 0.1)])
    model = _Model()
    agent = _agent(tmp_path, "off", skills, model, jev)
    assert agent.complete(prompt) == {"text": "ready", "model": "hermes-model"}
    assert jev.calls == []
    assert "skill_relevance" not in model.prompts[0]
    assert model.prompts[0] == assemble_completion_prompt(prompt, agent.skills.load())


def test_shadow_logs_the_winner_without_changing_the_prompt(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    prompt = "caller-secret-7c2e"
    skills = tmp_path / "skills-shadow"
    _write_skill(skills, "alpha", "Alpha skill")
    _write_skill(skills, "beta", "Beta skill")
    jev = _Jev(
        _with_guards(
            _wide("alpha", {"alpha": 0.5, "beta": 0.4, "none": 0.1}, 0.9, 0.1),
            _rerank_beta(),
        )
    )
    model = _Model()
    agent = _agent(tmp_path, "shadow", skills, model, jev)
    with caplog.at_level("INFO", logger="hermes.jev"):
        assert agent.complete(prompt) == {"text": "ready", "model": "hermes-model"}
    assert len(jev.calls) == 6
    state, questions = jev.calls[0]
    assert state["request"] == prompt
    assert prompt not in json.dumps(questions)
    assert questions["which"]["instructions"] == WHICH
    assert "none" in questions["which"]["criteria"]
    rerank_questions = jev.calls[1][1]
    assert rerank_questions["fits::beta"]["instructions"]["question"] == FITS_QUESTION
    assert prompt not in json.dumps(rerank_questions)
    inbound_state, inbound_questions = jev.calls[2]
    assert inbound_state == {"text": prompt}
    assert prompt not in json.dumps(inbound_questions)
    outbound_state, outbound_questions = jev.calls[4]
    assert outbound_state == {"text": "ready"}
    assert prompt not in json.dumps(outbound_questions)
    loaded = agent.skills.load()
    assert model.prompts[0] == assemble_completion_prompt(prompt, loaded)
    assert "skill_relevance" not in model.prompts[0]
    assert "Relevant to the current request" not in model.prompts[0]
    assert "suggested=beta" in caplog.text
    assert "reason=ok" in caplog.text
    assert "hermes_index=alpha,beta" in caplog.text
    assert "suggestion_in_prompt=false" in caplog.text
    assert "pack=guardrails" in caplog.text
    assert "side=inbound" in caplog.text
    assert "side=outbound" in caplog.text
    assert "route=pass" in caplog.text
    assert "enforced=false" in caplog.text
    assert prompt not in caplog.text
    assert "fedcba9876543210" not in caplog.text


def test_soft_mode_adds_the_advisory_block_and_keeps_the_index(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    prompt = "caller-secret-7c2e"
    skills = tmp_path / "skills-soft"
    _write_skill(skills, "alpha", "Alpha skill")
    _write_skill(skills, "beta", "Beta skill")
    jev = _Jev(
        _with_guards(
            _wide("alpha", {"alpha": 0.5, "beta": 0.4, "none": 0.1}, 0.9, 0.1),
            _rerank_beta(),
        )
    )
    model = _Model()
    agent = _agent(tmp_path, "soft", skills, model, jev)
    with caplog.at_level("INFO", logger="hermes.jev"):
        assert agent.complete(prompt) == {"text": "ready", "model": "hermes-model"}
    loaded = agent.skills.load()
    block = suggestion_block("beta")
    assert model.prompts[0] == assemble_completion_prompt(prompt, loaded, block)
    assert "- alpha (1.0.0): Alpha skill" in model.prompts[0]
    assert "- beta (1.0.0): Beta skill" in model.prompts[0]
    assert model.prompts[0].index(block) < model.prompts[0].index(REQUEST_HEADER)
    assert prompt not in block
    assert "suggested=beta" in caplog.text
    assert "suggestion_in_prompt=true" in caplog.text
    assert prompt not in caplog.text
    assert "fedcba9876543210" not in caplog.text


def test_soft_mode_says_when_nothing_fits(tmp_path: Path) -> None:
    skills = tmp_path / "skills-soft-gate"
    _write_skill(skills, "alpha", "Alpha skill")
    jev = _Jev(_with_guards(_wide("alpha", {"alpha": 0.7, "none": 0.3}, 0.1, 0.9)))
    model = _Model()
    agent = _agent(tmp_path, "soft", skills, model, jev)
    agent.complete("status")
    assert len(jev.calls) == 5
    assert suggestion_block(None) in model.prompts[0]
    assert ADVISORY_NONE in model.prompts[0]
    assert "Relevant to the current request" not in model.prompts[0]
    assert "- alpha (1.0.0): Alpha skill" in model.prompts[0]


def test_soft_jev_failure_omits_the_advisory_block(tmp_path: Path) -> None:
    skills = tmp_path / "skills-soft-error"
    _write_skill(skills, "alpha", "Alpha skill")
    jev = _Jev(_with_guards(JevError("Jev request failed", 429)))
    model = _Model()
    agent = _agent(tmp_path, "soft", skills, model, jev)
    assert agent.complete("status") == {"text": "ready", "model": "hermes-model"}
    assert "skill_relevance" not in model.prompts[0]
    assert model.prompts[0].endswith(f"{REQUEST_HEADER}\nstatus")


def test_soft_with_no_skills_still_screens_the_turn(tmp_path: Path) -> None:
    jev = _Jev(_with_guards())
    model = _Model()
    agent = _agent(tmp_path, "soft", tmp_path / "empty-soft", model, jev)
    agent.complete("status")
    assert len(jev.calls) == 4
    assert "skill_relevance" not in model.prompts[0]
    assert NO_SKILLS in model.prompts[0]


def test_shadow_with_a_low_gate_makes_one_skill_call(tmp_path: Path) -> None:
    skills = tmp_path / "skills-gate"
    _write_skill(skills, "alpha", "Alpha skill")
    jev = _Jev(_with_guards(_wide("alpha", {"alpha": 0.7, "none": 0.3}, 0.1, 0.9)))
    model = _Model()
    agent = _agent(tmp_path, "shadow", skills, model, jev)
    agent.complete("status")
    assert len(jev.calls) == 5
    assert "which" in jev.calls[0][1]
    assert "jailbreak" in jev.calls[1][1]
    assert "skill_relevance" not in model.prompts[0]


def test_shadow_with_no_skills_skips_the_skill_pack(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    jev = _Jev(_with_guards())
    model = _Model()
    agent = _agent(tmp_path, "shadow", tmp_path / "empty-skills", model, jev)
    with caplog.at_level("INFO", logger="hermes.jev"):
        agent.complete("status")
    assert len(jev.calls) == 4
    assert NO_SKILLS in model.prompts[0]
    assert "reason=no_skills" in caplog.text
    assert "suggestion_in_prompt=false" in caplog.text
    assert "route=pass" in caplog.text


def test_shadow_jev_failure_still_returns_the_model_text(tmp_path: Path) -> None:
    skills = tmp_path / "skills-error"
    _write_skill(skills, "alpha", "Alpha skill")
    jev = _Jev(_with_guards(JevError("Jev request failed", 429)))
    model = _Model()
    agent = _agent(tmp_path, "shadow", skills, model, jev)
    assert agent.complete("status") == {"text": "ready", "model": "hermes-model"}
    assert len(jev.calls) == 5
    assert model.prompts[0].endswith(f"{REQUEST_HEADER}\nstatus")


def test_shadow_malformed_jev_answer_still_returns_the_model_text(tmp_path: Path) -> None:
    skills = tmp_path / "skills-bad"
    _write_skill(skills, "alpha", "Alpha skill")
    jev = _Jev(_with_guards({"which": {}}))
    model = _Model()
    agent = _agent(tmp_path, "shadow", skills, model, jev)
    assert agent.complete("status") == {"text": "ready", "model": "hermes-model"}
    assert len(model.prompts) == 1


def test_shadow_logs_a_block_and_still_returns_the_model_text(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    prompt = "caller-secret-7c2e"
    skills = tmp_path / "skills-block"
    _write_skill(skills, "alpha", "Alpha skill")
    jev = _Jev(
        [
            _wide("alpha", {"alpha": 0.7, "none": 0.3}, 0.1, 0.9),
            _guard_block(),
            _router_frontier(),
            _guard_pass(),
        ]
    )
    model = _Model()
    agent = _agent(tmp_path, "shadow", skills, model, jev)
    with caplog.at_level("INFO", logger="hermes.jev"):
        assert agent.complete(prompt) == {"text": "ready", "model": "hermes-model"}
    assert "route=block" in caplog.text
    assert "side=inbound" in caplog.text
    assert "enforced=false" in caplog.text
    assert prompt not in caplog.text
    assert model.prompts[0].endswith(f"{REQUEST_HEADER}\n{prompt}")


def test_guardrail_error_in_shadow_still_returns_the_model_text(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    skills = tmp_path / "skills-guard-error-shadow"
    _write_skill(skills, "alpha", "Alpha skill")
    jev = _Jev(
        [
            _wide("alpha", {"alpha": 0.7, "none": 0.3}, 0.1, 0.9),
            JevError("Jev request failed", 429),
            _router_frontier(),
            _guard_pass(),
        ]
    )
    model = _Model()
    agent = _agent(tmp_path, "shadow", skills, model, jev)
    with caplog.at_level("INFO", logger="hermes.jev"):
        assert agent.complete("status") == {"text": "ready", "model": "hermes-model"}
    assert "route=review" in caplog.text
    assert "reason=jev_error" in caplog.text
    assert "enforced=false" in caplog.text
    assert len(model.prompts) == 1


def test_soft_inbound_block_does_not_call_the_model(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    prompt = "caller-secret-7c2e"
    skills = tmp_path / "skills-soft-block"
    _write_skill(skills, "alpha", "Alpha skill")
    jev = _Jev(
        [
            _wide("alpha", {"alpha": 0.7, "none": 0.3}, 0.1, 0.9),
            _guard_block(),
        ]
    )
    model = _Model()
    agent = _agent(tmp_path, "soft", skills, model, jev)
    with caplog.at_level("INFO", logger="hermes.jev"):
        result = agent.complete(prompt)
    assert result["text"] == BLOCK_TEXT
    assert prompt not in result["text"]
    assert model.prompts == []
    assert len(jev.calls) == 3
    assert "route=block" in caplog.text
    assert "enforced=true" in caplog.text
    assert prompt not in caplog.text


def test_soft_inbound_review_and_jev_error_withhold_the_model(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    skills = tmp_path / "skills-soft-review"
    _write_skill(skills, "alpha", "Alpha skill")
    review = _guard_pass()
    review["self_harm"] = {"type": "noul", "noul": 0.5}
    jev = _Jev([_wide("alpha", {"alpha": 0.7, "none": 0.3}, 0.1, 0.9), review])
    model = _Model()
    agent = _agent(tmp_path, "soft", skills, model, jev)
    assert agent.complete("status")["text"] == REVIEW_TEXT
    assert model.prompts == []

    failed = _Jev([_wide("alpha", {"alpha": 0.7, "none": 0.3}, 0.1, 0.9), JevError("down", 503)])
    failed_model = _Model()
    failed_agent = _agent(tmp_path, "soft", skills, failed_model, failed)
    with caplog.at_level("INFO", logger="hermes.jev"):
        assert failed_agent.complete("status")["text"] == REVIEW_TEXT
    assert failed_model.prompts == []
    assert "reason=jev_error" in caplog.text
    assert "enforced=true" in caplog.text


def test_soft_outbound_block_hides_the_model_reply(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    prompt = "caller-secret-7c2e"
    skills = tmp_path / "skills-soft-outbound"
    _write_skill(skills, "alpha", "Alpha skill")
    jev = _Jev(
        [
            _wide("alpha", {"alpha": 0.7, "none": 0.3}, 0.1, 0.9),
            _guard_pass(),
            _router_frontier(),
            _guard_block(),
        ]
    )
    model = _Model()
    agent = _agent(tmp_path, "soft", skills, model, jev)
    with caplog.at_level("INFO", logger="hermes.jev"):
        result = agent.complete(prompt)
    assert result["text"] == BLOCK_TEXT
    assert "ready" not in result["text"]
    assert len(model.prompts) == 1
    assert "side=outbound" in caplog.text
    assert "route=block" in caplog.text
    assert "enforced=true" in caplog.text
    assert prompt not in caplog.text


def _model_settings_with(values: dict[str, str]) -> object:
    return load_settings(values)


def test_mode_off_does_not_construct_a_jev_client(tmp_path: Path) -> None:
    agent = HermesAgent(
        _model_settings(tmp_path, tmp_path / "empty-skills"),
        chroma_client=ChromaClient("chromadb", 8000, opener=lambda request, timeout: None),
        model_client=_Model(),
    )
    assert agent.jev is None


class _SearchChroma:
    def __init__(self, matches: list[dict[str, object]]) -> None:
        self.matches = matches

    def query_documents(self, embedding: list[float], limit: int) -> list[dict[str, object]]:
        assert limit == 10
        return list(self.matches)


def _search_agent(tmp_path: Path, mode: str, jev: object, matches: list[dict[str, object]]) -> HermesAgent:
    values = {
        "HERMES_ENV": "test",
        "CHROMA_HOST": "chromadb",
        "HERMES_MEMORY_DIR": str(tmp_path / f"memory-search-{mode}"),
        "HERMES_SKILLS_DIR": str(tmp_path / "unused-skills"),
        "HERMES_JEV_MODE": mode,
    }
    if mode != "off":
        values["HERMES_JEV_API_KEY"] = "fedcba9876543210"
    return HermesAgent(
        load_settings(values),
        chroma_client=_SearchChroma(matches),
        jev_client=jev,
    )


def test_search_skips_jev_when_mode_is_off(tmp_path: Path) -> None:
    matches = [{"id": "note-1", "text": "tuesday meeting", "distance": 0.2}]
    jev = _Jev([])
    agent = _search_agent(tmp_path, "off", jev, matches)
    found = agent.search_documents("tuesday")
    assert found["matches"] == matches
    assert jev.calls == []


def test_shadow_logs_passage_judgments_and_returns_every_match(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    query = "query-secret-7c2e"
    passage = "passage-secret-9af1"
    matches = [
        {"id": "note-1", "text": passage, "distance": 0.2},
        {"id": "note-2", "text": "other note", "distance": 0.4},
    ]
    jev = _Jev(
        [
            {
                "helps::note-1": {"type": "noul", "noul": 0.8},
                "relevance::note-1": {"type": "score", "score": 2.4},
                "helps::note-2": {"type": "noul", "noul": 0.1},
                "relevance::note-2": {"type": "score", "score": 0.2},
            }
        ]
    )
    agent = _search_agent(tmp_path, "shadow", jev, matches)
    with caplog.at_level("INFO", logger="hermes.jev"):
        found = agent.search_documents(query)
    assert found["matches"] == matches
    assert len(jev.calls) == 1
    state, questions = jev.calls[0]
    assert state["query"] == query
    assert query not in json.dumps(questions)
    assert passage not in json.dumps(questions)
    assert "helps::note-1" in questions
    assert "relevance::note-2" in questions
    assert "pack=chroma-passage" in caplog.text
    assert "matches=note-1,note-2" in caplog.text
    assert "shown=note-1" in caplog.text
    assert "filtered=false" in caplog.text
    assert query not in caplog.text
    assert passage not in caplog.text
    assert "fedcba9876543210" not in caplog.text


def test_soft_search_returns_only_passages_that_state_an_answer(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    query = "query-secret-7c2e"
    weak = "passage-secret-9af1"
    matches = [
        {"id": "note-1", "text": "tuesday meeting", "distance": 0.2},
        {"id": "note-2", "text": weak, "distance": 0.4},
    ]
    jev = _Jev(
        [
            {
                "helps::note-1": {"type": "noul", "noul": 0.8},
                "relevance::note-1": {"type": "score", "score": 2.0},
                "helps::note-2": {"type": "noul", "noul": 0.05},
                "relevance::note-2": {"type": "score", "score": 1.9},
            }
        ]
    )
    agent = _search_agent(tmp_path, "soft", jev, matches)
    with caplog.at_level("INFO", logger="hermes.jev"):
        found = agent.search_documents(query)
    assert found["matches"] == [matches[0]]
    assert len(jev.calls) == 1
    assert query not in json.dumps(jev.calls[0][1])
    assert weak not in json.dumps(jev.calls[0][1])
    assert "shown=note-1" in caplog.text
    assert "filtered=true" in caplog.text
    assert "matches=note-1,note-2" in caplog.text
    assert query not in caplog.text
    assert weak not in caplog.text


def test_soft_search_with_only_weak_passages_returns_no_matches(tmp_path: Path) -> None:
    matches = [{"id": "note-1", "text": "tuesday meeting", "distance": 0.2}]
    jev = _Jev(
        [
            {
                "helps::note-1": {"type": "noul", "noul": 0.05},
                "relevance::note-1": {"type": "score", "score": 0.1},
            }
        ]
    )
    agent = _search_agent(tmp_path, "soft", jev, matches)
    found = agent.search_documents("tuesday")
    assert found["matches"] == []
    assert len(jev.calls) == 1


def test_soft_jev_failure_still_returns_every_match(tmp_path: Path) -> None:
    matches = [{"id": "note-1", "text": "tuesday meeting", "distance": 0.2}]
    jev = _Jev([JevError("Jev request failed", 429)])
    agent = _search_agent(tmp_path, "soft", jev, matches)
    found = agent.search_documents("tuesday")
    assert found["matches"] == matches
    assert len(jev.calls) == 1


def test_search_with_no_matches_makes_no_jev_call(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    jev = _Jev([])
    agent = _search_agent(tmp_path, "shadow", jev, [])
    with caplog.at_level("INFO", logger="hermes.jev"):
        found = agent.search_documents("tuesday")
    assert found["matches"] == []
    assert jev.calls == []
    assert "reason=no_matches" in caplog.text
    assert "filtered=false" in caplog.text


def test_search_jev_failure_still_returns_the_matches(tmp_path: Path) -> None:
    matches = [{"id": "note-1", "text": "tuesday meeting", "distance": 0.2}]
    jev = _Jev([JevError("Jev request failed", 429)])
    agent = _search_agent(tmp_path, "shadow", jev, matches)
    found = agent.search_documents("tuesday")
    assert found["matches"] == matches
    assert len(jev.calls) == 1


def test_complete_rejects_an_assembled_prompt_over_the_limit(tmp_path: Path) -> None:
    model = _Model()
    jev = _Jev([])
    agent = _agent(tmp_path, "shadow", tmp_path / "empty-skills", model, jev)
    with pytest.raises(ValueError, match="exceeds"):
        agent.complete("x" * MAX_PROMPT_CHARS)
    assert model.prompts == []
    assert jev.calls == []
