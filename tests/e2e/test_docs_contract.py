"""Documentation and diagram files exist and carry Mermaid diagrams."""

from pathlib import Path

MERMAID_FILES = (
    "docs/architecture/overview.md",
    "docs/architecture/current.md",
    "docs/architecture/planned.md",
    "docs/architecture/jev-system-one.md",
    "docs/architecture/cursor-account.md",
    "docs/architecture/grok-hermes.md",
    "docs/architecture/history/000-empty-workspace.md",
    "docs/architecture/history/001-containerized-stack.md",
    "docs/architecture/history/002-model-provider.md",
    "docs/architecture/history/003-skill-index-completions.md",
    "docs/architecture/history/004-jev-client-shadow.md",
    "docs/architecture/history/005-skill-suggestion-shadow.md",
    "docs/architecture/history/006-skill-suggestion-advisory.md",
    "docs/architecture/history/007-chroma-passage-shadow.md",
    "docs/architecture/history/008-chroma-passage-soft.md",
    "docs/architecture/history/009-guardrails-shadow.md",
    "docs/architecture/history/010-guardrails-soft.md",
    "docs/architecture/history/011-memory-write-shadow.md",
    "docs/architecture/history/012-memory-write-soft.md",
    "docs/architecture/history/013-tool-runner.md",
    "docs/architecture/history/014-tool-gate-shadow.md",
    "docs/architecture/history/015-tool-gate-soft.md",
    "docs/architecture/history/016-model-router-shadow.md",
    "docs/architecture/history/017-supervisor-shadow.md",
    "docs/architecture/history/018-supervisor-soft.md",
    "docs/architecture/history/019-mcp-server.md",
    "docs/architecture/history/020-grok-handoff.md",
    "docs/architecture/history/021-retrieval.md",
)

REQUIRED_FILES = (
    "README.md",
    "LICENSE",
    "docs/README.md",
    "docs/architecture/jev-system-one.md",
    "docs/deployment/docker.md",
    "docs/deployment/environments.md",
    "docs/deployment/ghcr.md",
    "docs/testing/strategy.md",
    "docs/testing/coverage.md",
    "docs/skills/skill-template.md",
    "docs/changelogs/CHANGELOG.md",
    ".github/PULL_REQUEST_TEMPLATE.md",
    "ci-cd/github-actions/test.yml",
    "ci-cd/github-actions/build.yml",
    "ci-cd/github-actions/release.yml",
    "ci-cd/github-actions/deploy.yml",
    ".github/workflows/test.yml",
    ".github/workflows/build.yml",
    ".github/workflows/release.yml",
    ".github/workflows/deploy.yml",
)


def test_required_docs_exist(repo_root: Path) -> None:
    missing = [relative for relative in REQUIRED_FILES if not (repo_root / relative).is_file()]
    assert missing == []


def test_overview_names_the_four_services(repo_root: Path) -> None:
    overview = (repo_root / "docs/architecture/overview.md").read_text(encoding="utf-8")
    for name in ("hermes-agent", "chromadb", "chroma-gate", "hermes-gateway"):
        assert name in overview
    assert "Python API" in overview
    assert "Recommended model setup" in overview
    assert "google/gemini-flash-latest" in overview
    assert "No model" in overview
    assert "overview.md" in (repo_root / "docs/README.md").read_text(encoding="utf-8")


def test_architecture_docs_include_mermaid(repo_root: Path) -> None:
    for relative in MERMAID_FILES:
        text = (repo_root / relative).read_text(encoding="utf-8")
        assert "```mermaid" in text, relative


def test_history_records_before_and_after(repo_root: Path) -> None:
    before = (repo_root / "docs/architecture/history/000-empty-workspace.md").read_text(encoding="utf-8")
    after = (repo_root / "docs/architecture/history/001-containerized-stack.md").read_text(encoding="utf-8")
    skill_index = (repo_root / "docs/architecture/history/003-skill-index-completions.md").read_text(
        encoding="utf-8"
    )
    current = (repo_root / "docs/architecture/current.md").read_text(encoding="utf-8")
    assert "Empty workspace" in before
    assert "hermes-net" in after
    assert "hermes-net" in current
    assert "chromadb" in current
    assert "skill index" in skill_index
    assert "skill index" in current
    jev_client = (repo_root / "docs/architecture/history/004-jev-client-shadow.md").read_text(encoding="utf-8")
    suggestion = (repo_root / "docs/architecture/history/005-skill-suggestion-shadow.md").read_text(
        encoding="utf-8"
    )
    assert "mode off" in jev_client
    advisory = (repo_root / "docs/architecture/history/006-skill-suggestion-advisory.md").read_text(
        encoding="utf-8"
    )
    assert "skill_relevance" in suggestion
    assert "skill_relevance" in advisory
    assert "jev.mode" in current
    assert "HERMES_JEV_MODE" in current
    assert "shadow" in current
    assert "skill_relevance" in current
    passages = (repo_root / "docs/architecture/history/007-chroma-passage-shadow.md").read_text(
        encoding="utf-8"
    )
    assert "chroma-passage" in passages
    assert "chroma-passage" in current
    soft_passages = (repo_root / "docs/architecture/history/008-chroma-passage-soft.md").read_text(
        encoding="utf-8"
    )
    assert "helping" in soft_passages
    assert "helping" in current
    guardrails = (repo_root / "docs/architecture/history/009-guardrails-shadow.md").read_text(
        encoding="utf-8"
    )
    assert "guardrails" in guardrails
    assert "guardrails" in current
    soft_guard = (repo_root / "docs/architecture/history/010-guardrails-soft.md").read_text(encoding="utf-8")
    assert "withholds" in soft_guard
    assert "withholds" in current
    memory = (repo_root / "docs/architecture/history/011-memory-write-shadow.md").read_text(encoding="utf-8")
    assert "memory-write" in memory
    assert "memory-write" in current
    soft_memory = (repo_root / "docs/architecture/history/012-memory-write-soft.md").read_text(
        encoding="utf-8"
    )
    assert "skips" in soft_memory
    assert "skips" in current
    runner = (repo_root / "docs/architecture/history/013-tool-runner.md").read_text(encoding="utf-8")
    assert "allowlist" in runner
    assert "allowlist" in current
    tool_gate = (repo_root / "docs/architecture/history/014-tool-gate-shadow.md").read_text(encoding="utf-8")
    assert "tool-call" in tool_gate
    assert "tool-call" in current
    soft_tools = (repo_root / "docs/architecture/history/015-tool-gate-soft.md").read_text(encoding="utf-8")
    assert "holds" in soft_tools
    assert "holds" in current
    router = (repo_root / "docs/architecture/history/016-model-router-shadow.md").read_text(encoding="utf-8")
    assert "model-router" in router
    assert "frontier" in router
    assert "model-router" in current
    assert "frontier" in current
    supervisor = (repo_root / "docs/architecture/history/017-supervisor-shadow.md").read_text(
        encoding="utf-8"
    )
    assert "supervisor" in supervisor
    assert "supervisor" in current
    soft_supervisor = (repo_root / "docs/architecture/history/018-supervisor-soft.md").read_text(
        encoding="utf-8"
    )
    assert "stops" in soft_supervisor
    assert "stops" in current
    assert "mcp.enabled" in current
    assert "/mcp" in current
    assert "grok.handoff" in current
    assert "delegate_to_grok" in current
    handoff = (repo_root / "docs/architecture/history/020-grok-handoff.md").read_text(encoding="utf-8")
    assert "202" in handoff
    retrieval = (repo_root / "docs/architecture/history/021-retrieval.md").read_text(encoding="utf-8")
    for name in ("HERMES_RAG_MODE", "HERMES_MEMORY_INDEX", "HERMES_EMBED_MODEL", "migrate-documents"):
        assert name in retrieval
        assert name in current


def test_jev_plan_keeps_hermes_in_control(repo_root: Path) -> None:
    plan = (repo_root / "docs/architecture/jev-system-one.md").read_text(encoding="utf-8")
    planned = (repo_root / "docs/architecture/planned.md").read_text(encoding="utf-8")
    assert "under Hermes control" in plan
    assert "does not become the agent" in plan
    assert "HERMES_JEV_MODE" in plan
    assert "jev-system-one.md" in planned
    assert "Jev is not the model behind" in planned
    assert "Later improvements" in plan
    assert "Later improvements" in planned
    assert "tests/test_data/router/tasks.json" in planned
    assert "hermes-gateway" in planned
    cursor = (repo_root / "docs/architecture/cursor-account.md").read_text(encoding="utf-8")
    assert "Cursor opens the connection" in cursor
    assert "does not use Cursor's LLM" in cursor
    assert "MCP is the account connection" in cursor
    assert "cursor-sdk" in cursor
    assert "delete_memory" in cursor
    assert "HERMES_MODEL_NAME" in cursor
    assert "does not become a Cursor agent" in cursor
    assert "cursor-account.md" in planned
    grok = (repo_root / "docs/architecture/grok-hermes.md").read_text(encoding="utf-8")
    assert "api.hermes.newplanetit.com.au" in grok
    assert "9119" in grok
    assert "delegate_to_grok" in grok
    assert "X-Agent-Alias-Token" in grok
    assert "grok-hermes.md" in planned
