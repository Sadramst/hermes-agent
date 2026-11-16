"""Environment-backed settings for the Hermes Agent."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlparse

from utils.time import check_timezone


class SettingsError(ValueError):
    """Raised when Hermes configuration is missing or invalid."""


ENV_DEFAULT_DIRS: dict[str, tuple[str, str]] = {
    "dev": ("storage/memory", "storage/skills"),
    "test": ("/tmp/hermes-test/memory", "/tmp/hermes-test/skills"),
    "prod": ("/app/storage/memory", "/app/storage/skills"),
}
ENV_DEFAULT_PROFILE_DIRS: dict[str, str] = {
    "dev": "gateway",
    "test": "/tmp/hermes-test/gateway",
    "prod": "/app/gateway",
}
PROVIDER_AUTH_MODES = {
    "api_key",
    "openrouter",
    "google_ai_studio",
    "nous_portal",
    "claude_oauth",
    "chatgpt_oauth",
    "gemini_subscription_pending",
}

LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
REQUIRED_VARIABLES = ("HERMES_ENV", "CHROMA_HOST")
MIN_CHROMA_TOKEN_LENGTH = 16
MODEL_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}")
MODEL_VARIABLES = ("HERMES_MODEL_BASE_URL", "HERMES_MODEL_NAME", "HERMES_MODEL_API_KEY")
MCP_MODES = {"off", "on"}
MAX_MCP_HOSTS = 8
_MCP_HOST = re.compile(
    r"([A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*)"
    r"(?::([0-9]{1,5}))?"
)
EMBED_VARIABLES = ("HERMES_EMBED_BASE_URL", "HERMES_EMBED_MODEL", "HERMES_EMBED_API_KEY")
RAG_MODES = {"off", "shadow", "soft"}
MEMORY_INDEX_MODES = {"off", "on"}
COLLECTION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{1,61}[A-Za-z0-9]")
# Hash vectors and provider vectors have different dimensions, so each gets its own collection.
HASH_COLLECTIONS = ("hermes-documents", "hermes-memory")
PROVIDER_COLLECTIONS = ("hermes-documents-v2", "hermes-memory-v2")


@dataclass(frozen=True)
class Settings:
    hermes_env: str
    chroma_host: str
    chroma_port: int
    memory_dir: str
    skills_dir: str
    chroma_auth_token: str | None
    api_token: str | None
    model_base_url: str | None
    model_name: str | None
    model_api_key: str | None
    log_level: str
    hermes_host: str
    hermes_port: int
    mcp_enabled: bool
    mcp_allowed_hosts: tuple[str, ...]
    embed_base_url: str | None = None
    embed_model: str | None = None
    embed_api_key: str | None = None
    embed_input_type: bool = False
    documents_collection: str = HASH_COLLECTIONS[0]
    memory_collection: str = HASH_COLLECTIONS[1]
    rag_mode: str = "off"
    memory_index: bool = False
    profile_dir: str = ""
    timezone: str = "UTC"
    provider_auth_mode: str = "api_key"


def load_settings(environ: Mapping[str, str] | None = None) -> Settings:
    """Load settings from the process environment or an explicit mapping."""
    source = os.environ if environ is None else environ
    missing = [name for name in REQUIRED_VARIABLES if not str(source.get(name, "")).strip()]
    if missing:
        joined = ", ".join(missing)
        raise SettingsError(f"Missing required environment variables: {joined}")

    hermes_env = str(source["HERMES_ENV"]).strip()
    if hermes_env not in ENV_DEFAULT_DIRS:
        raise SettingsError(f"Invalid HERMES_ENV: {hermes_env}")

    default_memory, default_skills = ENV_DEFAULT_DIRS[hermes_env]
    default_profile = ENV_DEFAULT_PROFILE_DIRS[hermes_env]
    token = str(source.get("CHROMA_AUTH_TOKEN", "")).strip()
    if hermes_env == "prod" and not chroma_token_usable(token):
        raise SettingsError("CHROMA_AUTH_TOKEN is required when HERMES_ENV is prod")
    api_token = _optional_secret(source, "HERMES_API_TOKEN", hermes_env == "prod")
    model_base_url, model_name, model_api_key = _model_provider(source, hermes_env == "prod")
    log_level = str(source.get("HERMES_LOG_LEVEL", "INFO")).strip().upper()
    if log_level not in LOG_LEVELS:
        raise SettingsError("Invalid HERMES_LOG_LEVEL")
    mcp_enabled, mcp_allowed_hosts = _mcp(source, api_token)
    embed_base_url, embed_model, embed_api_key = _embedder(source)
    documents_collection, memory_collection = _collections(source, embed_model is not None)
    timezone_name = _timezone(source)
    provider_auth_mode = _provider_auth_mode(source)

    return Settings(
        hermes_env=hermes_env,
        chroma_host=str(source["CHROMA_HOST"]).strip(),
        chroma_port=_port(source, "CHROMA_PORT", 8000),
        memory_dir=str(source.get("HERMES_MEMORY_DIR", default_memory)).strip() or default_memory,
        skills_dir=str(source.get("HERMES_SKILLS_DIR", default_skills)).strip() or default_skills,
        chroma_auth_token=token or None,
        api_token=api_token,
        model_base_url=model_base_url,
        model_name=model_name,
        model_api_key=model_api_key,
        log_level=log_level,
        hermes_host=str(source.get("HERMES_HOST", "0.0.0.0")).strip() or "0.0.0.0",
        hermes_port=_port(source, "HERMES_PORT", 8080),
        mcp_enabled=mcp_enabled,
        mcp_allowed_hosts=mcp_allowed_hosts,
        embed_base_url=embed_base_url,
        embed_model=embed_model,
        embed_api_key=embed_api_key,
        embed_input_type=_switch(source, "HERMES_EMBED_INPUT_TYPE"),
        documents_collection=documents_collection,
        memory_collection=memory_collection,
        rag_mode=_choice(source, "HERMES_RAG_MODE", RAG_MODES),
        memory_index=_switch(source, "HERMES_MEMORY_INDEX"),
        profile_dir=str(source.get("HERMES_PROFILE_DIR", default_profile)).strip() or default_profile,
        timezone=timezone_name,
        provider_auth_mode=provider_auth_mode,
    )


def chroma_token_usable(token: str) -> bool:
    """Return True when a secret is long enough and has no whitespace."""
    return len(token) >= MIN_CHROMA_TOKEN_LENGTH and not any(character.isspace() for character in token)


def _optional_secret(source: Mapping[str, str], name: str, required: bool) -> str | None:
    value = str(source.get(name, "")).strip()
    if required and not chroma_token_usable(value):
        raise SettingsError(f"{name} is required when HERMES_ENV is prod")
    if value and not chroma_token_usable(value):
        raise SettingsError(f"Invalid {name}")
    return value or None


def _model_provider(source: Mapping[str, str], required: bool) -> tuple[str | None, str | None, str | None]:
    base_url = str(source.get("HERMES_MODEL_BASE_URL", "")).strip()
    name = str(source.get("HERMES_MODEL_NAME", "")).strip()
    api_key = str(source.get("HERMES_MODEL_API_KEY", "")).strip()
    provided = (bool(base_url), bool(name), bool(api_key))
    if required and not all(provided):
        raise SettingsError("A model provider is required when HERMES_ENV is prod")
    if any(provided) and not all(provided):
        joined = ", ".join(MODEL_VARIABLES)
        raise SettingsError(f"{joined} must be set together")
    if not any(provided):
        return None, None, None
    if not chroma_token_usable(api_key):
        raise SettingsError("Invalid HERMES_MODEL_API_KEY")
    if not MODEL_NAME.fullmatch(name):
        raise SettingsError("Invalid HERMES_MODEL_NAME")
    return _base_url(base_url, "HERMES_MODEL_BASE_URL"), name, api_key


def _embedder(source: Mapping[str, str]) -> tuple[str | None, str | None, str | None]:
    base_url = str(source.get("HERMES_EMBED_BASE_URL", "")).strip()
    name = str(source.get("HERMES_EMBED_MODEL", "")).strip()
    api_key = str(source.get("HERMES_EMBED_API_KEY", "")).strip()
    provided = (bool(base_url), bool(name), bool(api_key))
    if not any(provided):
        return None, None, None
    if not all(provided):
        joined = ", ".join(EMBED_VARIABLES)
        raise SettingsError(f"{joined} must be set together")
    if not chroma_token_usable(api_key):
        raise SettingsError("Invalid HERMES_EMBED_API_KEY")
    if not MODEL_NAME.fullmatch(name):
        raise SettingsError("Invalid HERMES_EMBED_MODEL")
    return _base_url(base_url, "HERMES_EMBED_BASE_URL"), name, api_key


def _collections(source: Mapping[str, str], provider: bool) -> tuple[str, str]:
    defaults = PROVIDER_COLLECTIONS if provider else HASH_COLLECTIONS
    documents = _collection(source, "HERMES_DOCUMENTS_COLLECTION", defaults[0])
    memory = _collection(source, "HERMES_MEMORY_COLLECTION", defaults[1])
    if documents == memory:
        raise SettingsError("HERMES_DOCUMENTS_COLLECTION and HERMES_MEMORY_COLLECTION must differ")
    return documents, memory


def _collection(source: Mapping[str, str], name: str, default: str) -> str:
    value = str(source.get(name, "")).strip() or default
    if not COLLECTION.fullmatch(value):
        raise SettingsError(f"Invalid {name}")
    return value


def _choice(source: Mapping[str, str], name: str, allowed: set[str]) -> str:
    value = str(source.get(name, "off")).strip().lower() or "off"
    if value not in allowed:
        raise SettingsError(f"Invalid {name}: {value}")
    return value


def _switch(source: Mapping[str, str], name: str) -> bool:
    return _choice(source, name, MEMORY_INDEX_MODES) == "on"


def _base_url(value: str, name: str) -> str:
    normalized = value.rstrip("/")
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise SettingsError(f"Invalid {name}")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise SettingsError(f"Invalid {name}")
    return normalized


def _mcp(source: Mapping[str, str], api_token: str | None) -> tuple[bool, tuple[str, ...]]:
    raw = str(source.get("HERMES_MCP_ENABLED", "off")).strip().lower() or "off"
    if raw not in MCP_MODES:
        raise SettingsError(f"Invalid HERMES_MCP_ENABLED: {raw}")
    enabled = raw == "on"
    if enabled and api_token is None:
        raise SettingsError("HERMES_API_TOKEN is required when HERMES_MCP_ENABLED is on")
    return enabled, _mcp_hosts(str(source.get("HERMES_MCP_ALLOWED_HOSTS", "")))


def _mcp_hosts(raw: str) -> tuple[str, ...]:
    text = raw.strip()
    if not text:
        return ()
    parts = [part.strip() for part in text.split(",")]
    if any(not part for part in parts) or len(parts) > MAX_MCP_HOSTS:
        raise SettingsError("Invalid HERMES_MCP_ALLOWED_HOSTS")
    hosts: list[str] = []
    for part in parts:
        match = _MCP_HOST.fullmatch(part)
        if match is None:
            raise SettingsError("Invalid HERMES_MCP_ALLOWED_HOSTS")
        port = match.group(2)
        if port is not None and not 1 <= int(port) <= 65535:
            raise SettingsError("Invalid HERMES_MCP_ALLOWED_HOSTS")
        hosts.append(part)
    return tuple(hosts)


def _port(source: Mapping[str, str], name: str, default: int) -> int:
    raw = str(source.get(name, str(default))).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise SettingsError(f"Invalid {name}") from exc
    if not 1 <= value <= 65535:
        raise SettingsError(f"Invalid {name}")
    return value


def _timezone(source: Mapping[str, str]) -> str:
    raw = str(source.get("HERMES_TIMEZONE") or source.get("TZ") or "UTC").strip() or "UTC"
    try:
        return check_timezone(raw)
    except ValueError as exc:
        raise SettingsError("Invalid HERMES_TIMEZONE") from exc


def _provider_auth_mode(source: Mapping[str, str]) -> str:
    raw = str(source.get("HERMES_PROVIDER_AUTH_MODE", "api_key")).strip().lower() or "api_key"
    if raw not in PROVIDER_AUTH_MODES:
        raise SettingsError(f"Invalid HERMES_PROVIDER_AUTH_MODE: {raw}")
    return raw
