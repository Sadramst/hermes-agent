"""Completion route and the Hermes API credential."""

from pathlib import Path

from fastapi.testclient import TestClient

from agent.prompt import NO_SKILLS, REQUEST_HEADER, SKILLS_HEADER
from api.app import create_app
from services.model import MAX_PROMPT_CHARS, ModelError
from utils.settings import load_settings

TOKEN = "fedcba9876543210"
MODEL_KEY = "0123456789abcdef"


def _settings(tmp_path: Path, token: str = "") -> object:
    values = {
        "HERMES_ENV": "test",
        "CHROMA_HOST": "chromadb",
        "CHROMA_PORT": "8000",
        "HERMES_API_TOKEN": token,
        "HERMES_MODEL_BASE_URL": "https://models.example/v1",
        "HERMES_MODEL_NAME": "hermes-model",
        "HERMES_MODEL_API_KEY": MODEL_KEY,
        "HERMES_MEMORY_DIR": str(tmp_path / "memory"),
        "HERMES_SKILLS_DIR": str(tmp_path / "skills"),
    }
    return load_settings(values)


def _write_skill(tmp_path: Path, name: str = "demo") -> None:
    skill_dir = tmp_path / "skills" / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\nversion: 0.1.0\n---\n# Purpose\n{name} skill.\n",
        encoding="utf-8",
    )


class _Model:
    def __init__(self, text: str = "ready") -> None:
        self.text = text
        self.model = "hermes-model"
        self.prompts: list[str] = []

    def complete(self, prompt: str, *, model: str | None = None) -> str:
        self.prompts.append(prompt)
        if self.text == "down":
            raise ModelError("upstream secret", 500)
        return self.text


class _Chroma:
    def upsert_chunks(self, ids: list[str], texts: list[str], embeddings: list, metadatas: list) -> None:
        return None

    def delete_source(self, field: str, value: str) -> None:
        return None

    def source_metadatas(self, field: str, value: str) -> list[dict[str, object]]:
        return []

    def query_documents(self, embedding: list[float], limit: int) -> list[dict[str, object]]:
        return []


def test_completion_returns_provider_text(tmp_path: Path) -> None:
    model = _Model()
    client = TestClient(
        create_app(
            _settings(tmp_path),
            chroma_reachable=lambda: True,
            chroma_client=_Chroma(),
            model_client=model,
        )
    )
    response = client.post("/completions", json={"prompt": "status"})
    assert response.status_code == 200
    assert response.json() == {"text": "ready", "model": "hermes-model"}
    assert len(model.prompts) == 1
    assert model.prompts[0].startswith(f"{SKILLS_HEADER}\n{NO_SKILLS}")
    assert model.prompts[0].endswith(f"{REQUEST_HEADER}\nstatus")


def test_completion_includes_the_loaded_skill_index(tmp_path: Path) -> None:
    _write_skill(tmp_path)
    model = _Model()
    client = TestClient(
        create_app(
            _settings(tmp_path),
            chroma_reachable=lambda: True,
            chroma_client=_Chroma(),
            model_client=model,
        )
    )
    response = client.post("/completions", json={"prompt": "status"})
    assert response.status_code == 200
    assembled = model.prompts[0]
    assert "- demo (0.1.0): demo skill." in assembled
    assert assembled.endswith(f"{REQUEST_HEADER}\nstatus")


def test_completion_requires_the_api_credential_when_configured(tmp_path: Path) -> None:
    model = _Model()
    client = TestClient(
        create_app(
            _settings(tmp_path, TOKEN),
            chroma_reachable=lambda: True,
            chroma_client=_Chroma(),
            model_client=model,
        )
    )
    denied = client.post("/completions", json={"prompt": "status"})
    assert denied.status_code == 401
    health = client.get("/health")
    assert health.status_code == 200
    assert TOKEN not in health.text
    assert MODEL_KEY not in health.text
    allowed = client.post(
        "/completions",
        json={"prompt": "status"},
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    assert allowed.status_code == 200


def test_documents_require_the_same_credential(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            _settings(tmp_path, TOKEN),
            chroma_reachable=lambda: True,
            chroma_client=_Chroma(),
            model_client=_Model(),
        )
    )
    missing = client.post("/documents", json={"id": "note-1", "text": "tuesday"})
    assert missing.status_code == 401
    search = client.get("/documents/search", params={"q": "tuesday"})
    assert search.status_code == 401
    wrong = client.post(
        "/documents",
        json={"id": "note-1", "text": "tuesday"},
        headers={"Authorization": "Bearer fedcba9876543211"},
    )
    assert wrong.status_code == 401
    saved = client.post(
        "/documents",
        json={"id": "note-1", "text": "tuesday"},
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    assert saved.status_code == 201


def test_unconfigured_provider_is_unavailable() -> None:
    settings = load_settings({"HERMES_ENV": "test", "CHROMA_HOST": "chromadb"})
    client = TestClient(create_app(settings, chroma_reachable=lambda: True, chroma_client=_Chroma()))
    response = client.post("/completions", json={"prompt": "status"})
    assert response.status_code == 503
    assert "not configured" in response.text


def test_provider_failure_is_a_bad_gateway(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            _settings(tmp_path),
            chroma_reachable=lambda: True,
            chroma_client=_Chroma(),
            model_client=_Model("down"),
        )
    )
    response = client.post("/completions", json={"prompt": "status"})
    assert response.status_code == 502
    assert "upstream secret" not in response.text


def test_assembled_prompt_over_the_limit_is_rejected(tmp_path: Path) -> None:
    model = _Model()
    client = TestClient(
        create_app(
            _settings(tmp_path),
            chroma_reachable=lambda: True,
            chroma_client=_Chroma(),
            model_client=model,
        )
    )
    response = client.post("/completions", json={"prompt": "x" * MAX_PROMPT_CHARS})
    assert response.status_code == 400
    assert "exceeds" in response.text
    assert model.prompts == []
