"""Compose, image, and script contracts. These tests do not need a Docker daemon."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

COMPOSE_FILES = {
    "dev": "docker/docker-compose.dev.yml",
    "test": "docker/docker-compose.test.yml",
    "prod": "docker/docker-compose.prod.yml",
}
REQUIRED_MOUNT_TARGETS = {"/app/storage/memory", "/app/storage/skills", "/data"}


def _load(repo_root: Path, relative: str) -> dict:
    return yaml.safe_load((repo_root / relative).read_text(encoding="utf-8"))


def _targets(compose: dict) -> set[str]:
    found: set[str] = set()
    for service in compose["services"].values():
        for volume in service.get("volumes") or []:
            found.add(_target(volume))
    return found


def _target(volume: object) -> str:
    if isinstance(volume, dict):
        return str(volume["target"])
    parts = str(volume).split(":")
    if parts[-1] in {"ro", "rw"}:
        return parts[-2]
    return parts[-1]


def _env_files(service: dict) -> list[str]:
    value = service.get("env_file")
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    found: list[str] = []
    for item in value:
        if isinstance(item, dict):
            found.append(str(item.get("path", "")))
        else:
            found.append(str(item))
    return found


def test_each_environment_defines_the_stack(repo_root: Path) -> None:
    for env_name, relative in COMPOSE_FILES.items():
        compose = _load(repo_root, relative)
        services = compose["services"]
        agent = services["hermes-agent"]
        chroma = services["chromadb"]

        assert "hermes-net" in compose["networks"]
        assert compose["networks"]["hermes-net"]["name"] == f"hermes-{env_name}-net"
        assert "hermes-net" in agent["networks"]
        if env_name == "prod":
            assert agent["environment"]["CHROMA_HOST"] == "chroma-gate"
            assert "chroma-net" in chroma["networks"]
            assert "hermes-net" not in chroma["networks"]
            assert compose["networks"]["chroma-net"]["name"] == "hermes-prod-chroma-net"
        else:
            assert agent["environment"]["CHROMA_HOST"] == "chromadb"
            assert "hermes-net" in chroma["networks"]
        assert REQUIRED_MOUNT_TARGETS <= _targets(compose)
        assert agent["cap_drop"] == ["ALL"]
        assert agent["healthcheck"]["test"]
        assert chroma["healthcheck"]["test"]
        assert any(f".env.{env_name}" in item for item in _env_files(agent))
        assert "chromadb/chroma" in str(chroma["image"])
        chroma_health = " ".join(str(part) for part in chroma["healthcheck"]["test"])
        assert "api/v2/heartbeat" in chroma_health
        assert "python" not in chroma_health
        assert "hermes-agent" in str(agent["image"])
        assert str(agent["image"]).startswith("ghcr.io/")

        if env_name == "prod":
            assert "build" not in agent
            assert "${GHCR_OWNER:?GHCR_OWNER is required}" in agent["image"]
            assert "${IMAGE_TAG:?IMAGE_TAG is required}" in agent["image"]
            assert agent["restart"] == "unless-stopped"
            assert chroma["restart"] == "unless-stopped"
            assert any("8569" in str(port) for port in agent["ports"])
            assert "ports" not in chroma
            gate = services["chroma-gate"]
            assert gate["entrypoint"] == ["python3", "-m", "services.chroma_gate"]
            assert "CHROMA_AUTH_TOKEN" in str(agent["environment"]["CHROMA_AUTH_TOKEN"])
            assert "CHROMA_AUTH_TOKEN" in str(chroma["environment"]["CHROMA_AUTH_TOKEN"])
            assert "CHROMA_AUTH_TOKEN" in str(gate["environment"]["CHROMA_AUTH_TOKEN"])
            assert "HERMES_API_TOKEN" in str(agent["environment"]["HERMES_API_TOKEN"])
            assert "HERMES_MODEL_BASE_URL" in str(agent["environment"]["HERMES_MODEL_BASE_URL"])
            assert "HERMES_MODEL_NAME" in str(agent["environment"]["HERMES_MODEL_NAME"])
            assert "HERMES_MODEL_API_KEY" in str(agent["environment"]["HERMES_MODEL_API_KEY"])
            assert "HERMES_PROFILE_DIR" in agent["environment"]
            assert "hermes-net" in gate["networks"]
            assert "chroma-net" in gate["networks"]
            assert "ports" not in gate
            gateway = services["hermes-gateway"]
            assert "env/.env.gateway" in _env_files(gateway)
            assert gateway["command"] == ["gateway", "run"]
            assert gateway["environment"]["HERMES_DASHBOARD"] == "1"
            assert gateway["environment"]["OPENROUTER_API_KEY"] == "${OPENROUTER_API_KEY:-}"
            assert gateway["environment"]["NVIDIA_API_KEY"] == "${NVIDIA_API_KEY:-}"
            assert "GEMINI_API_KEY" in gateway["environment"]["GOOGLE_API_KEY"]
            assert "GITHUB_COPILOT_TOKEN" in gateway["environment"]["COPILOT_GITHUB_TOKEN"]
            assert "TELEGRAM_BOT_TOKEN" not in gateway["environment"]
            assert any("9119" in str(port) for port in gateway["ports"])
            assert any("8642" in str(port) for port in gateway["ports"])
            assert "nousresearch/hermes-agent" in str(gateway["image"])
        elif env_name == "test":
            assert agent["build"]["target"] == "runtime"
            assert agent["restart"] == "no"
            assert "ports" not in agent
            assert "ports" not in chroma
            tests = services["hermes-tests"]
            assert tests["build"]["target"] == "test"
            assert "not integration" in " ".join(tests["command"])
            assert tests["restart"] == "no"
        else:
            assert agent["build"]["target"] == "runtime"
            assert agent["restart"] == "unless-stopped"
            assert chroma["restart"] == "unless-stopped"
            assert any("8080" in str(port) for port in agent["ports"])
            assert any("8000" in str(port) for port in chroma["ports"])


def test_dockerfile_is_multistage_ubuntu_and_non_root(repo_root: Path) -> None:
    text = (repo_root / "docker" / "Dockerfile").read_text(encoding="utf-8")
    stages = _stages(text)
    assert "ubuntu:24.04" in stages["builder"][0]
    assert "ubuntu:24.04" in stages["runtime"][0]
    runtime_body = stages["runtime"][1]
    assert "COPY gateway /app/gateway" in runtime_body
    assert "USER hermes" in runtime_body
    assert "USER root" not in runtime_body
    assert "HEALTHCHECK" in runtime_body
    assert "pytest" in stages["test"][1]


def test_build_push_and_deploy_scripts(repo_root: Path) -> None:
    build = (repo_root / "docker" / "scripts" / "build.sh").read_text(encoding="utf-8")
    push = (repo_root / "docker" / "scripts" / "push.sh").read_text(encoding="utf-8")
    assert "ghcr.io/" in build
    assert "GHCR_OWNER" in build
    assert "IMAGE_TAG" in build
    assert "--target runtime" in build
    assert "docker push" in push
    assert "ghcr.io/" in push
    deploy = (repo_root / "docker" / "scripts" / "deploy.sh").read_text(encoding="utf-8")
    assert ".env.gateway.example" in deploy
    assert "chmod 600" in deploy
    gitignore = (repo_root / ".gitignore").read_text(encoding="utf-8")
    assert "docker/env/.env.gateway" in gitignore
    gateway_env = (repo_root / "docker" / "env" / ".env.gateway.example").read_text(encoding="utf-8")
    for var in ("OPENROUTER_API_KEY", "GOOGLE_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_ALLOWED_USERS"):
        assert var in gateway_env


def test_heartbeat_paths_match_vector_db_config(repo_root: Path) -> None:
    from services.chroma import ChromaClient

    config = yaml.safe_load((repo_root / "vector-db" / "config" / "chroma.yaml").read_text(encoding="utf-8"))
    assert list(ChromaClient.HEARTBEAT_PATHS) == config["heartbeat_paths"]
    assert ChromaClient.COLLECTION_NAME == config["collection"]


def _stages(text: str) -> dict[str, tuple[str, str]]:
    stages: dict[str, tuple[str, str]] = {}
    for chunk in re.split(r"(?m)^FROM ", text):
        if not chunk.strip():
            continue
        header, _, body = chunk.partition("\n")
        match = re.search(r"\bAS\s+(\w+)", header, re.IGNORECASE)
        name = match.group(1) if match else "default"
        stages[name] = (header, body)
    return stages
