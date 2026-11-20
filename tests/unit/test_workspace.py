"""Unit and HTTP contract tests for sandboxed multi-project workspace management."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent.core import HermesAgent
from agent.tools import ASK_TEXT, ToolCall, agent_tool_schemas
from api.app import create_app
from services.model import ModelToolCall, ModelTurn
from services.workspace import (
    WorkspaceConfirmationRequired,
    WorkspaceDisabledError,
    WorkspaceManager,
    WorkspacePermissionError,
)
from utils.settings import SettingsError, load_settings

TOKEN = "fedcba9876543210"
MODEL_KEY = "0123456789abcdef"


class _FakeChroma:
    def heartbeat(self) -> bool:
        return True


class _ScriptedWorkspaceModel:
    model = "google/gemini-2.5-flash"

    def __init__(self, turns: list[ModelTurn]) -> None:
        self.turns = list(turns)
        self.calls: list[tuple[list[dict[str, object]], list[dict[str, object]] | None]] = []

    def complete(self, prompt: str, *, model: str | None = None) -> str:
        return "done"

    def chat(
        self,
        messages: list[dict[str, object]],
        *,
        tools: list[dict[str, object]] | None = None,
        model: str | None = None,
    ) -> ModelTurn:
        self.calls.append((list(messages), tools))
        return self.turns[len(self.calls) - 1]


def _seed_workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "workspace"
    alpha = ws / "alpha"
    (alpha / ".git").mkdir(parents=True)
    (alpha / ".git" / "config").write_text("[core]\n\trepositoryformatversion = 0\n", encoding="utf-8")
    (alpha / "src").mkdir()
    (alpha / "src" / "app.py").write_text("def greet():\n    return 'hello brain'\n", encoding="utf-8")
    (alpha / "README.md").write_text("# Alpha Project\nCore service.\n", encoding="utf-8")
    (alpha / ".env").write_text("SECRET=should_never_leak\n", encoding="utf-8")
    (alpha / ".env.prod").write_text("API_KEY=topsecret\n", encoding="utf-8")
    (alpha / ".env.example").write_text("API_KEY=example\n", encoding="utf-8")
    (alpha / "tls.key").write_text("PRIVATE KEY", encoding="utf-8")
    (alpha / "node_modules" / "pkg").mkdir(parents=True)
    (alpha / "node_modules" / "pkg" / "index.js").write_text("console.log('ignored')", encoding="utf-8")
    (ws / ".hidden").mkdir()
    return ws


def test_workspace_settings_validation(tmp_path: Path) -> None:
    default = load_settings({"HERMES_ENV": "dev", "CHROMA_HOST": "localhost"})
    assert default.workspace_mode == "off"
    assert default.projects_dir == ""

    with pytest.raises(SettingsError, match="HERMES_WORKSPACE_MODE"):
        load_settings({"HERMES_ENV": "dev", "CHROMA_HOST": "localhost", "HERMES_WORKSPACE_MODE": "admin"})

    with pytest.raises(SettingsError, match="HERMES_PROJECTS_DIR"):
        load_settings({"HERMES_ENV": "dev", "CHROMA_HOST": "localhost", "HERMES_WORKSPACE_MODE": "rw"})

    with pytest.raises(SettingsError, match="HERMES_WORKSPACE_ALLOWED_CMDS"):
        load_settings(
            {
                "HERMES_ENV": "dev",
                "CHROMA_HOST": "localhost",
                "HERMES_PROJECTS_DIR": str(tmp_path),
                "HERMES_WORKSPACE_MODE": "ro",
                "HERMES_WORKSPACE_ALLOWED_CMDS": "/bin/sh",
            }
        )

    ok = load_settings(
        {
            "HERMES_ENV": "dev",
            "CHROMA_HOST": "localhost",
            "HERMES_PROJECTS_DIR": str(tmp_path),
            "HERMES_WORKSPACE_MODE": "rw",
            "HERMES_WORKSPACE_ALLOWED_CMDS": "git,pytest",
        }
    )
    assert ok.workspace_mode == "rw"
    assert ok.workspace_allowed_cmds == ("git", "pytest")


def test_workspace_manager_blocks_secrets_traversal_and_enforces_ro_vs_rw(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ws = _seed_workspace(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text("outside secret", encoding="utf-8")

    disabled = WorkspaceManager(ws, mode="off")
    with pytest.raises(WorkspaceDisabledError):
        disabled.list_projects()

    ro = WorkspaceManager(ws, mode="ro")
    assert ro.project_count() == 1
    assert ro.list_projects() == [{"name": "alpha", "is_git": True, "has_readme": True}]
    files = ro.list_files("alpha")
    assert "README.md" in files
    assert "src/app.py" in files
    assert ".env.example" in files
    assert ".env" not in files
    assert ".env.prod" not in files
    assert ".git/config" not in files
    assert "tls.key" not in files
    assert "node_modules/pkg/index.js" not in files

    # Read allowed file and search
    read_res = ro.read_file("alpha", "src/app.py", start_line=1, end_line=2)
    assert "hello brain" in str(read_res["content"])
    assert ro.search_files("alpha", "hello") == [{"path": "src/app.py", "line": 2, "snippet": "return 'hello brain'"}]
    assert ro.search_files("alpha", "topsecret") == []

    # Secret files, traversal, and write attempts fail closed
    for forbidden in (".env", ".env.prod", ".ENV.prod", ".git/config", "tls.key", "auth.json", "../outside.txt", "/etc/passwd"):
        with pytest.raises(WorkspacePermissionError):
            ro.read_file("alpha", forbidden)

    with pytest.raises(WorkspacePermissionError, match="read-only"):
        ro.write_file("alpha", "README.md", "nope")
    with pytest.raises(WorkspacePermissionError, match="read-only"):
        ro.run_command("alpha", ["git", "status"])

    # Binary refusal
    (ws / "alpha" / "blob.bin").write_bytes(b"\x00\x01\x02bin")
    with pytest.raises(ValueError, match="Binary"):
        ro.read_file("alpha", "blob.bin")

    # RW writes & command allowlist + confirmation gating
    rw = WorkspaceManager(ws, mode="rw")
    written = rw.write_file("alpha", "notes/todo.md", "- ship v0.6.0\n", create_dirs=True)
    assert written["bytes"] > 0
    assert (ws / "alpha" / "notes" / "todo.md").read_text(encoding="utf-8") == "- ship v0.6.0\n"

    with pytest.raises(WorkspacePermissionError, match="secret"):
        rw.write_file("alpha", ".env.local", "BAD=1")
    with pytest.raises(WorkspacePermissionError, match="allowlist"):
        rw.run_command("alpha", ["curl", "https://example.com"])
    with pytest.raises(WorkspacePermissionError, match="Path-qualified"):
        rw.run_command("alpha", ["/bin/sh", "-c", "id"])

    for destructive in (
        ["rm", "-rf", "."],
        ["git", "push", "--force", "origin", "main"],
        ["git", "reset", "--hard", "HEAD~1"],
        ["git", "clean", "-fd"],
        ["git", "branch", "-D", "feat"],
    ):
        with pytest.raises(WorkspaceConfirmationRequired):
            rw.run_command("alpha", destructive)

    # Deterministic subprocess execution verification (shell=False, cwd=alpha)
    recorded: dict[str, object] = {}

    def fake_run(argv, *, cwd, shell, capture_output, text, timeout, encoding, errors):  # noqa: ANN001
        recorded["argv"] = argv
        recorded["cwd"] = cwd
        recorded["shell"] = shell
        return subprocess.CompletedProcess(argv, 0, stdout="On branch main\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    exec_res = rw.run_command("alpha", ["git", "status", "-sb"])
    assert exec_res["returncode"] == 0
    assert exec_res["stdout"] == "On branch main\n"
    assert recorded["shell"] is False
    assert Path(str(recorded["cwd"])) == (ws / "alpha").resolve()

    if shutil.which("git"):
        monkeypatch.undo()
        real = rw.run_command("alpha", ["git", "--version"])
        assert real["returncode"] == 0
        assert "git version" in str(real["stdout"]).lower()


def test_agent_loop_workspace_tools_and_confirmation_gate(repo_root: Path, tmp_path: Path) -> None:
    ws = _seed_workspace(tmp_path)
    assert len(agent_tool_schemas("off")) == 9
    assert len(agent_tool_schemas("ro")) == 13
    assert len(agent_tool_schemas("rw")) == 15

    settings = load_settings(
        {
            "HERMES_ENV": "test",
            "CHROMA_HOST": "chromadb",
            "HERMES_MEMORY_DIR": str(tmp_path / "memory"),
            "HERMES_SKILLS_DIR": str(repo_root / "storage" / "skills"),
            "HERMES_PROFILE_DIR": str(repo_root / "gateway"),
            "HERMES_PROJECTS_DIR": str(ws),
            "HERMES_WORKSPACE_MODE": "rw",
            "HERMES_MODEL_BASE_URL": "https://openrouter.ai/api/v1",
            "HERMES_MODEL_NAME": "google/gemini-2.5-flash",
            "HERMES_MODEL_API_KEY": MODEL_KEY,
        }
    )
    model = _ScriptedWorkspaceModel(
        [
            ModelTurn(
                content="",
                tool_calls=[
                    ModelToolCall(id="w1", name="list_projects", arguments={}),
                    ModelToolCall(id="w2", name="read_project_file", arguments={"project": "alpha", "path": "README.md"}),
                    ModelToolCall(
                        id="w3",
                        name="write_project_file",
                        arguments={"project": "alpha", "path": "docs/plan.md", "content": "# Plan\n"},
                    ),
                ],
            ),
            ModelTurn(
                content="",
                tool_calls=[
                    ModelToolCall(
                        id="w4",
                        name="run_project_command",
                        arguments={"project": "alpha", "command": "git reset --hard"},
                    )
                ],
            ),
            ModelTurn(content="Paused before running git reset --hard; confirmation required.", tool_calls=[]),
        ]
    )
    agent = HermesAgent(settings, chroma_client=_FakeChroma(), model_client=model)  # type: ignore[arg-type]
    result = agent.run_agent("Inspect alpha, create docs/plan.md, and reset.")
    assert "confirmation required" in str(result["text"]).lower()
    assert [s["name"] for s in result["steps"]] == [
        "list_projects",
        "read_project_file",
        "write_project_file",
        "run_project_command",
    ]
    assert result["steps"][3]["status"] == "ask_person"
    assert ASK_TEXT in str(result["steps"][3]["output"])
    assert (ws / "alpha" / "docs" / "plan.md").read_text(encoding="utf-8") == "# Plan\n"
    assert "project workspace tools are active" in str(model.calls[0][0][0]["content"]).lower()
    assert len(model.calls[0][1] or []) == 15

    # Refused tool batch test
    bad = agent.run_tools([ToolCall("read_project_file", {"project": "alpha", "path": ".env.prod"})])
    assert bad[0].status == "refused"


def test_http_projects_endpoints_enforce_auth_mode_and_secrets(tmp_path: Path) -> None:
    ws = _seed_workspace(tmp_path)
    ro_settings = load_settings(
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
    ro_client = TestClient(create_app(ro_settings, chroma_reachable=lambda: True, chroma_client=_FakeChroma()))  # type: ignore[arg-type]
    assert ro_client.get("/projects").status_code == 401
    health = ro_client.get("/health").json()
    assert health["workspace"] == {"enabled": True, "mode": "ro", "project_count": 1}
    assert str(ws) not in str(health)

    headers = {"Authorization": f"Bearer {TOKEN}"}
    assert ro_client.get("/projects", headers=headers).status_code == 200
    assert ro_client.get("/projects/alpha/read", params={"path": ".env"}, headers=headers).status_code == 403
    assert ro_client.post(
        "/projects/alpha/write",
        json={"path": "x.txt", "content": "hi"},
        headers=headers,
    ).status_code == 403
    assert ro_client.post(
        "/projects/alpha/exec",
        json={"argv": ["git", "status"]},
        headers=headers,
    ).status_code == 403

    rw_settings = load_settings(
        {
            "HERMES_ENV": "test",
            "CHROMA_HOST": "chromadb",
            "HERMES_API_TOKEN": TOKEN,
            "HERMES_MEMORY_DIR": str(tmp_path / "memory"),
            "HERMES_SKILLS_DIR": str(tmp_path / "skills"),
            "HERMES_PROJECTS_DIR": str(ws),
            "HERMES_WORKSPACE_MODE": "rw",
        }
    )
    rw_client = TestClient(create_app(rw_settings, chroma_reachable=lambda: True, chroma_client=_FakeChroma()))  # type: ignore[arg-type]
    wrote = rw_client.post(
        "/projects/alpha/write",
        json={"path": "hello.txt", "content": "world"},
        headers=headers,
    )
    assert wrote.status_code == 200
    confirm = rw_client.post(
        "/projects/alpha/exec",
        json={"argv": ["rm", "-rf", "."]},
        headers=headers,
    )
    assert confirm.status_code == 409
    missing = rw_client.get("/projects/unknown/files", headers=headers)
    assert missing.status_code == 404
