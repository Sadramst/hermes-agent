from utils.settings import load_settings


def test_model_small_optional() -> None:
    base = {
        "HERMES_ENV": "test",
        "CHROMA_HOST": "chromadb",
    }
    off = load_settings(base)
    assert off.model_small is None
    on = load_settings({**base, "HERMES_MODEL_SMALL": "openrouter/cheap"})
    assert on.model_small == "openrouter/cheap"
