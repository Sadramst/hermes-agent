"""Documentation, gateway templates, and Mermaid diagram contracts."""

from pathlib import Path

MERMAID_FILES = (
    "README.md",
    "docs/architecture/personal-assistant.md",
    "docs/architecture/telegram-gateway.md",
    "docs/architecture/providers-and-subscriptions.md",
    "docs/deployment/ubuntu-server.md",
)

REQUIRED_FILES = (
    "README.md",
    "LICENSE",
    "docs/README.md",
    "docs/architecture/personal-assistant.md",
    "docs/architecture/telegram-gateway.md",
    "docs/architecture/providers-and-subscriptions.md",
    "docs/deployment/ubuntu-server.md",
    "docs/changelogs/CHANGELOG.md",
    "gateway/SOUL.md",
    "gateway/USER.md",
    "gateway/config.yaml.example",
    "gateway/cron.yaml.example",
    "docker/scripts/bootstrap-gateway.sh",
    ".github/workflows/test.yml",
    ".github/workflows/build.yml",
    ".github/workflows/release.yml",
    ".github/workflows/deploy.yml",
)


def test_required_docs_and_gateway_templates_exist(repo_root: Path) -> None:
    missing = [relative for relative in REQUIRED_FILES if not (repo_root / relative).is_file()]
    assert missing == []


def test_architecture_and_deploy_docs_include_mermaid(repo_root: Path) -> None:
    for relative in MERMAID_FILES:
        text = (repo_root / relative).read_text(encoding="utf-8")
        assert "```mermaid" in text, relative


def test_personal_customization_clears_legacy_upstream_references(repo_root: Path) -> None:
    forbidden = ("newplanetit.com.au", "5011-Hermes", "your-github-org")
    for folder in ("README.md", "docs", "gateway", "docker", "storage/skills"):
        target = repo_root / folder
        paths = [target] if target.is_file() else [p for p in target.rglob("*") if p.is_file()]
        for path in paths:
            content = path.read_text(encoding="utf-8")
            for needle in forbidden:
                assert needle not in content, f"{needle!r} leaked in {path}"


def test_personal_gateway_and_provider_docs_cover_telegram_and_gemini_status(repo_root: Path) -> None:
    soul = (repo_root / "gateway/SOUL.md").read_text(encoding="utf-8")
    user = (repo_root / "gateway/USER.md").read_text(encoding="utf-8")
    providers = (repo_root / "docs/architecture/providers-and-subscriptions.md").read_text(encoding="utf-8")
    telegram = (repo_root / "docs/architecture/telegram-gateway.md").read_text(encoding="utf-8")

    assert "Sadra" in soul
    assert "hermes-api" in soul
    assert "non-custodial" in soul.lower()
    assert "Sadramst" in user
    assert "finance.*" in user
    assert "Not live yet" in providers
    assert "Claude" in providers and "ChatGPT" in providers
    assert "TELEGRAM_BOT_TOKEN" in telegram
    assert "bootstrap-gateway.sh" in telegram
