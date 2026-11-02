"""Settings resolution for DEV, TEST, and PROD."""

import pytest

from utils.settings import SettingsError, load_settings

PROD = {
    "HERMES_ENV": "prod",
    "CHROMA_HOST": "chroma-gate",
    "CHROMA_AUTH_TOKEN": "0123456789abcdef",
    "HERMES_API_TOKEN": "fedcba9876543210",
    "HERMES_MODEL_BASE_URL": "https://models.example/v1",
    "HERMES_MODEL_NAME": "hermes-model",
    "HERMES_MODEL_API_KEY": "0123456789abcdef",
}


def _prod(**extra: str) -> dict[str, str]:
    merged = dict(PROD)
    merged.update(extra)
    return merged


def test_dev_test_prod_resolve_distinct_paths_and_hosts() -> None:
    dev = load_settings({"HERMES_ENV": "dev", "CHROMA_HOST": "localhost"})
    test = load_settings({"HERMES_ENV": "test", "CHROMA_HOST": "chromadb"})
    prod = load_settings(_prod(CHROMA_HOST="chroma.internal"))

    assert len({dev.memory_dir, test.memory_dir, prod.memory_dir}) == 3
    assert len({dev.skills_dir, test.skills_dir, prod.skills_dir}) == 3
    assert len({dev.chroma_host, test.chroma_host, prod.chroma_host}) == 3
    assert dev.chroma_port == 8000
    assert dev.chroma_auth_token is None
    assert dev.api_token is None
    assert dev.model_base_url is None
    assert prod.api_token == "fedcba9876543210"
    assert prod.model_base_url == "https://models.example/v1"
    assert prod.model_name == "hermes-model"
    assert prod.jev_mode == "off"
    assert prod.jev_api_key is None
    assert prod.jev_model == "jev-1.13.0"
    assert prod.jev_base_url == "https://api.typesafe.ai/v1"


def test_missing_required_env_raises() -> None:
    with pytest.raises(SettingsError, match="HERMES_ENV"):
        load_settings({"CHROMA_HOST": "chromadb"})
    with pytest.raises(SettingsError, match="CHROMA_HOST"):
        load_settings({"HERMES_ENV": "dev"})


def test_invalid_environment_name_raises() -> None:
    with pytest.raises(SettingsError, match="HERMES_ENV"):
        load_settings({"HERMES_ENV": "staging", "CHROMA_HOST": "chromadb"})


def test_explicit_paths_and_port_override_defaults() -> None:
    settings = load_settings(
        _prod(
            CHROMA_HOST="chromadb",
            HERMES_MEMORY_DIR="/data/memory",
            HERMES_SKILLS_DIR="/data/skills",
            CHROMA_PORT="9000",
        )
    )
    assert settings.memory_dir == "/data/memory"
    assert settings.skills_dir == "/data/skills"
    assert settings.chroma_port == 9000
    assert settings.chroma_auth_token == "0123456789abcdef"


def test_prod_requires_a_long_chroma_token() -> None:
    with pytest.raises(SettingsError, match="CHROMA_AUTH_TOKEN"):
        load_settings(_prod(CHROMA_AUTH_TOKEN=""))
    with pytest.raises(SettingsError, match="CHROMA_AUTH_TOKEN"):
        load_settings(_prod(CHROMA_AUTH_TOKEN="short"))


def test_prod_requires_an_api_token_and_a_model_provider() -> None:
    with pytest.raises(SettingsError, match="HERMES_API_TOKEN"):
        load_settings(_prod(HERMES_API_TOKEN=""))
    with pytest.raises(SettingsError, match="model provider"):
        load_settings(_prod(HERMES_MODEL_BASE_URL="", HERMES_MODEL_NAME="", HERMES_MODEL_API_KEY=""))


def test_model_provider_fields_must_be_set_together() -> None:
    with pytest.raises(SettingsError, match="must be set together"):
        load_settings(
            {
                "HERMES_ENV": "dev",
                "CHROMA_HOST": "localhost",
                "HERMES_MODEL_BASE_URL": "https://models.example/v1",
            }
        )


def test_model_provider_rejects_a_short_key_and_a_credential_in_the_url() -> None:
    with pytest.raises(SettingsError, match="HERMES_MODEL_API_KEY"):
        load_settings(
            {
                "HERMES_ENV": "dev",
                "CHROMA_HOST": "localhost",
                "HERMES_MODEL_BASE_URL": "https://models.example/v1",
                "HERMES_MODEL_NAME": "hermes-model",
                "HERMES_MODEL_API_KEY": "short",
            }
        )
    with pytest.raises(SettingsError, match="HERMES_MODEL_BASE_URL"):
        load_settings(
            {
                "HERMES_ENV": "dev",
                "CHROMA_HOST": "localhost",
                "HERMES_MODEL_BASE_URL": "https://user:secret@models.example/v1",
                "HERMES_MODEL_NAME": "hermes-model",
                "HERMES_MODEL_API_KEY": "0123456789abcdef",
            }
        )


def test_dev_rejects_a_short_api_token() -> None:
    with pytest.raises(SettingsError, match="HERMES_API_TOKEN"):
        load_settings({"HERMES_ENV": "dev", "CHROMA_HOST": "localhost", "HERMES_API_TOKEN": "short"})


def test_jev_mode_off_does_not_require_a_key() -> None:
    settings = load_settings({"HERMES_ENV": "dev", "CHROMA_HOST": "localhost", "HERMES_JEV_MODE": "off"})
    assert settings.jev_mode == "off"
    assert settings.jev_api_key is None


def test_jev_shadow_requires_a_key_and_rejects_aliases() -> None:
    with pytest.raises(SettingsError, match="HERMES_JEV_API_KEY"):
        load_settings({"HERMES_ENV": "dev", "CHROMA_HOST": "localhost", "HERMES_JEV_MODE": "shadow"})
    with pytest.raises(SettingsError, match="HERMES_JEV_API_KEY"):
        load_settings(
            {
                "HERMES_ENV": "dev",
                "CHROMA_HOST": "localhost",
                "HERMES_JEV_MODE": "soft",
                "HERMES_JEV_API_KEY": "short",
            }
        )
    with pytest.raises(SettingsError, match="pinned"):
        load_settings(
            {
                "HERMES_ENV": "dev",
                "CHROMA_HOST": "localhost",
                "HERMES_JEV_MODE": "shadow",
                "HERMES_JEV_API_KEY": "0123456789abcdef",
                "HERMES_JEV_MODEL": "jev-latest",
            }
        )
    with pytest.raises(SettingsError, match="HERMES_JEV_BASE_URL"):
        load_settings(
            {
                "HERMES_ENV": "dev",
                "CHROMA_HOST": "localhost",
                "HERMES_JEV_BASE_URL": "https://user:secret@api.typesafe.ai/v1",
                "HERMES_JEV_API_KEY": "0123456789abcdef",
            }
        )


def test_invalid_port_raises() -> None:
    with pytest.raises(SettingsError, match="CHROMA_PORT"):
        load_settings({"HERMES_ENV": "dev", "CHROMA_HOST": "chromadb", "CHROMA_PORT": "0"})
