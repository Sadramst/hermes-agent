"""Documentation, AGENTS.md builder/runner manual, Mini PC architecture, and Mermaid contracts."""

from pathlib import Path

MERMAID_FILES = (
    "AGENTS.md",
    "README.md",
    "docs/DEPLOYMENT.md",
    "docs/MINIPC_ARCHITECTURE.md",
)

REQUIRED_FILES = (
    "AGENTS.md",
    "README.md",
    "LICENSE",
    "docs/DEPLOYMENT.md",
    "docs/MINIPC_ARCHITECTURE.md",
    "docs/CHANGELOG.md",
    "vector-db/chromadb/README.md",
    "gateway/SOUL.md",
    "gateway/USER.md",
    "gateway/config.yaml.example",
    "gateway/cron.yaml.example",
    "docker/docker-compose.minipc.yml",
    "docker/env/.env.minipc.example",
    "docker/scripts/bootstrap-gateway.sh",
    "docker/scripts/setup-minipc.sh",
    "docker/scripts/sync-brain.sh",
    "docker/scripts/backup-brain.sh",
    ".github/workflows/test.yml",
    ".github/workflows/build.yml",
    ".github/workflows/release.yml",
    ".github/workflows/deploy.yml",
)


def test_required_docs_and_gateway_templates_exist(repo_root: Path) -> None:
    missing = [relative for relative in REQUIRED_FILES if not (repo_root / relative).is_file()]
    assert missing == []


def test_builder_and_deploy_docs_include_mermaid(repo_root: Path) -> None:
    for relative in MERMAID_FILES:
        text = (repo_root / relative).read_text(encoding="utf-8")
        assert "```mermaid" in text, relative


def test_personal_customization_clears_legacy_upstream_references(repo_root: Path) -> None:
    forbidden = ("newplanetit.com.au", "5011-Hermes", "your-github-org")
    for folder in ("AGENTS.md", "README.md", "docs", "gateway", "docker", "storage/skills"):
        target = repo_root / folder
        paths = [target] if target.is_file() else [p for p in target.rglob("*") if p.is_file()]
        for path in paths:
            content = path.read_text(encoding="utf-8")
            for needle in forbidden:
                assert needle not in content, f"{needle!r} leaked in {path}"


def test_builder_manual_and_minipc_docs_cover_telegram_remote_and_gemini_status(
    repo_root: Path,
) -> None:
    agents_md = (repo_root / "AGENTS.md").read_text(encoding="utf-8")
    readme = (repo_root / "README.md").read_text(encoding="utf-8")
    soul = (repo_root / "gateway/SOUL.md").read_text(encoding="utf-8")
    user = (repo_root / "gateway/USER.md").read_text(encoding="utf-8")
    deploy_doc = (repo_root / "docs/DEPLOYMENT.md").read_text(encoding="utf-8")
    minipc_doc = (repo_root / "docs/MINIPC_ARCHITECTURE.md").read_text(encoding="utf-8")

    assert "AGENTS.md" in readme
    assert "TELEGRAM_BOT_TOKEN" in agents_md
    assert "setup-minipc.sh" in agents_md
    assert "Tailscale" in agents_md
    assert "bootstrap-gateway.sh" in agents_md
    assert "not live yet" in agents_md.lower()
    assert "Claude" in agents_md and "ChatGPT" in agents_md
    assert "hermes-api" in soul
    assert "/workspace" in soul
    assert "non-custodial" in soul.lower()
    assert "USER.md" in soul
    assert "finance.*" in user
    assert "/workspace" in user
    assert "TELEGRAM_BOT_TOKEN" in deploy_doc
    assert "not live yet" in deploy_doc.lower()
    assert "Tailscale" in minipc_doc and "Cloudflare" in minipc_doc
    assert "/knowledge" in minipc_doc and "/workspace" in minipc_doc
