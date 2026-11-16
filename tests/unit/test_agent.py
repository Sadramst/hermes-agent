"""Agent wiring keeps memory and skills inside their directories."""

from pathlib import Path

import pytest

from agent.core import HermesAgent
from agent.prompt import NO_SKILLS, REQUEST_HEADER, assemble_completion_prompt
from services.chroma import ChromaClient
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
    assert model.prompts[0] == assemble_completion_prompt("status", agent.skills.load())
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


def test_complete_rejects_an_assembled_prompt_over_the_limit(tmp_path: Path) -> None:
    model = _Model()
    agent = HermesAgent(
        _model_settings(tmp_path, tmp_path / "empty-skills"),
        chroma_client=ChromaClient("chromadb", 8000, opener=lambda request, timeout: None),
        model_client=model,
    )
    with pytest.raises(ValueError, match="exceeds"):
        agent.complete("x" * MAX_PROMPT_CHARS)
    assert model.prompts == []
