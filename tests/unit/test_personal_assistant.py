"""Tests for generic personal assistant profile, timezone clock, providers, tools, skills, and CLI."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent.core import HermesAgent
from agent.profile import PersonalProfile, build_agent_system_prompt, load_personal_profile
from agent.tools import TOOL_ARGUMENTS
from api.app import create_app
from cli.main import main as cli_main
from services.model import ModelToolCall, ModelTurn
from skills.loader import SkillLoader
from utils.settings import SettingsError, load_settings
from utils.time import check_timezone, now_report

TOKEN = "fedcba9876543210"
MODEL_KEY = "0123456789abcdef"

REQUIRED_HEADINGS = (
    "Purpose",
    "Inputs",
    "Outputs",
    "Execution flow",
    "Error handling",
    "Logging",
    "Versioning",
    "Test coverage",
    "Documentation references",
)


class _FakeChroma:
    def heartbeat(self) -> bool:
        return True

    def query_documents(self, embedding: list[float], limit: int) -> list[dict[str, object]]:
        return []


class _InspectingChatModel:
    model = "google/gemini-2.5-flash"

    def __init__(self) -> None:
        self.messages_seen: list[list[dict[str, object]]] = []

    def complete(self, prompt: str, *, model: str | None = None) -> str:
        return "single"

    def chat(
        self,
        messages: list[dict[str, object]],
        *,
        tools: list[dict[str, object]] | None = None,
        model: str | None = None,
    ) -> ModelTurn:
        self.messages_seen.append(list(messages))
        if len(self.messages_seen) == 1:
            return ModelTurn(
                content="",
                tool_calls=[
                    ModelToolCall(id="t1", name="current_time", arguments={}),
                    ModelToolCall(id="t2", name="list_memories", arguments={"prefix": "finance."}),
                ],
            )
        return ModelTurn(content="Checked clock and finance keys.", tool_calls=[])


def test_timezone_validation_and_clock_report() -> None:
    assert check_timezone("UTC") == "UTC"
    assert check_timezone("UTC+08:00") == "UTC+08:00"
    assert check_timezone("Asia/Singapore") == "Asia/Singapore"
    with pytest.raises(ValueError, match="HERMES_TIMEZONE"):
        check_timezone("Not A Timezone!")

    fixed = datetime(2026, 11, 16, 6, 30, tzinfo=timezone.utc)
    report = now_report("Asia/Singapore", now_utc=fixed)
    assert report["date"] == "2026-11-16"
    assert report["local_iso"].endswith("+08:00")
    assert report["utc_iso"] == "2026-11-16T06:30:00+00:00"


def test_settings_accept_personal_fields_and_reject_invalid_values(tmp_path: Path) -> None:
    settings = load_settings(
        {
            "HERMES_ENV": "dev",
            "CHROMA_HOST": "localhost",
            "HERMES_PROFILE_DIR": str(tmp_path),
            "HERMES_TIMEZONE": "UTC+08:00",
            "HERMES_PROVIDER_AUTH_MODE": "openrouter",
        }
    )
    assert settings.profile_dir == str(tmp_path)
    assert settings.timezone == "UTC+08:00"
    assert settings.provider_auth_mode == "openrouter"

    with pytest.raises(SettingsError, match="HERMES_TIMEZONE"):
        load_settings({"HERMES_ENV": "dev", "CHROMA_HOST": "localhost", "HERMES_TIMEZONE": "bad tz"})

    with pytest.raises(SettingsError, match="HERMES_PROVIDER_AUTH_MODE"):
        load_settings(
            {"HERMES_ENV": "dev", "CHROMA_HOST": "localhost", "HERMES_PROVIDER_AUTH_MODE": "unofficial_hack"}
        )


def test_profile_system_prompt_stays_generic_and_injects_user_profile(repo_root: Path, tmp_path: Path) -> None:
    generic_prompt = build_agent_system_prompt(PersonalProfile(soul="", user=""))
    assert "Sadra" not in generic_prompt
    assert "non-custodial" in generic_prompt.lower()

    profile = load_personal_profile(repo_root / "gateway")
    assert profile.loaded is True
    assert "Everyday Personal Assistant" in profile.soul
    assert "Sadramst" in profile.user

    system_prompt = build_agent_system_prompt(
        profile,
        timezone_name="Asia/Singapore",
        provider_auth_mode="openrouter",
    )
    assert "SOUL.md" in system_prompt
    assert "USER.md" in system_prompt
    assert "non-custodial" in system_prompt.lower()

    settings = load_settings(
        {
            "HERMES_ENV": "test",
            "CHROMA_HOST": "chromadb",
            "HERMES_MEMORY_DIR": str(tmp_path / "memory"),
            "HERMES_SKILLS_DIR": str(repo_root / "storage" / "skills"),
            "HERMES_PROFILE_DIR": str(repo_root / "gateway"),
            "HERMES_TIMEZONE": "Asia/Singapore",
            "HERMES_PROVIDER_AUTH_MODE": "openrouter",
            "HERMES_MODEL_BASE_URL": "https://openrouter.ai/api/v1",
            "HERMES_MODEL_NAME": "google/gemini-2.5-flash",
            "HERMES_MODEL_API_KEY": MODEL_KEY,
        }
    )
    model = _InspectingChatModel()
    agent = HermesAgent(settings, chroma_client=_FakeChroma(), model_client=model)  # type: ignore[arg-type]
    agent.remember("finance.runway", "12 months cash reserve")
    agent.remember("work.api", "hermes-agent v0.5.0")

    result = agent.run_agent("Check today's date and my finance notes")
    assert result["text"] == "Checked clock and finance keys."
    assert model.messages_seen[0][0]["role"] == "system"
    assert "USER.md" in str(model.messages_seen[0][0]["content"])
    assert [s["name"] for s in result["steps"]] == ["current_time", "list_memories"]
    assert result["steps"][1]["output"] == "finance.runway"


def test_http_routes_for_providers_memories_and_health(repo_root: Path, tmp_path: Path) -> None:
    settings = load_settings(
        {
            "HERMES_ENV": "test",
            "CHROMA_HOST": "chromadb",
            "HERMES_API_TOKEN": TOKEN,
            "HERMES_MEMORY_DIR": str(tmp_path / "memory"),
            "HERMES_SKILLS_DIR": str(repo_root / "storage" / "skills"),
            "HERMES_PROFILE_DIR": str(repo_root / "gateway"),
            "HERMES_TIMEZONE": "Asia/Singapore",
            "HERMES_PROVIDER_AUTH_MODE": "google_ai_studio",
            "HERMES_MODEL_BASE_URL": "https://generativelanguage.googleapis.com/v1beta/openai",
            "HERMES_MODEL_NAME": "gemini-2.5-flash",
            "HERMES_MODEL_API_KEY": MODEL_KEY,
        }
    )
    client = TestClient(create_app(settings, chroma_reachable=lambda: True, chroma_client=_FakeChroma()))  # type: ignore[arg-type]

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["provider"]["auth_mode"] == "google_ai_studio"
    assert health.json()["provider"]["gemini_subscription"] == "pending_official_oauth"
    assert health.json()["assistant"] == {"timezone": "Asia/Singapore", "profile_loaded": True}
    assert MODEL_KEY not in health.text
    assert TOKEN not in health.text

    assert client.get("/providers").status_code == 401
    assert client.get("/memories").status_code == 401

    headers = {"Authorization": f"Bearer {TOKEN}"}
    prov = client.get("/providers", headers=headers)
    assert prov.status_code == 200
    assert prov.json()["gemini_subscription"]["supported_today"] is False
    assert prov.json()["gemini_subscription"]["status"] == "pending_official_nous_google_oauth"
    assert MODEL_KEY not in prov.text

    assert client.post(
        "/tools",
        json={"calls": [{"name": "remember", "arguments": {"key": "goal.focus", "value": "Deep work"}}]},
        headers=headers,
    ).status_code == 200
    memories = client.get("/memories", params={"prefix": "goal."}, headers=headers)
    assert memories.status_code == 200
    assert memories.json() == {"keys": ["goal.focus"]}


def test_all_everyday_skills_stay_generic_and_follow_contract(repo_root: Path) -> None:
    skills = SkillLoader(repo_root / "storage" / "skills").load()
    names = {skill.name for skill in skills}
    assert names == {
        "autonomous-problem-solver",
        "bootstrap-hermes-stack",
        "personal-development-coach",
        "personal-financial-advisor",
        "software-engineering-architect",
    }
    for skill in skills:
        assert "sadra" not in skill.body.lower(), f"Hardcoded user leaked in {skill.name}"
        for heading in REQUIRED_HEADINGS:
            assert f"# {heading}" in skill.body, f"{skill.name} missing # {heading}"


def test_cli_personal_subcommands(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("HERMES_ENV", "test")
    monkeypatch.setenv("CHROMA_HOST", "chromadb")
    monkeypatch.setenv("HERMES_MEMORY_DIR", str(tmp_path / "memory"))
    monkeypatch.setenv("HERMES_SKILLS_DIR", str(tmp_path / "skills"))
    monkeypatch.setenv("HERMES_PROVIDER_AUTH_MODE", "openrouter")

    assert cli_main(["remember", "finance.emergency", "6 months"]) == 0
    assert json.loads(capsys.readouterr().out) == {"key": "finance.emergency", "stored": True}

    assert cli_main(["memories", "--prefix", "finance."]) == 0
    assert json.loads(capsys.readouterr().out) == {"keys": ["finance.emergency"]}

    assert cli_main(["recall", "finance.emergency"]) == 0
    assert capsys.readouterr().out.strip() == "6 months"

    assert cli_main(["recall", "finance.missing"]) == 1
    capsys.readouterr()

    assert cli_main(["providers"]) == 0
    provider_json = json.loads(capsys.readouterr().out)
    assert provider_json["auth_mode"] == "openrouter"
    assert provider_json["gemini_subscription"]["supported_today"] is False
    assert set(TOOL_ARGUMENTS) >= {"list_memories", "current_time"}
