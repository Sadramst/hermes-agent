"""Command line interface for health checks, skill listing, and collection maintenance."""

from __future__ import annotations

import argparse
import json

from agent.core import HermesAgent
from utils.settings import load_settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hermes")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("health", help="Print the agent health report as JSON")
    subcommands.add_parser("skills", help="List skills from the skills directory")
    migrate = subcommands.add_parser(
        "migrate-documents",
        help="Copy documents from an older collection into the active one and embed them again",
    )
    migrate.add_argument("--from", dest="source", required=True, help="Source collection name")
    subcommands.add_parser(
        "reindex-memory",
        help="Index every memory file into the memory collection (HERMES_MEMORY_INDEX=on)",
    )
    args = parser.parse_args(argv)
    agent = HermesAgent(load_settings())

    if args.command == "health":
        report = agent.health()
        print(json.dumps(report, sort_keys=True))
        return 0

    if args.command == "migrate-documents":
        print(json.dumps(agent.migrate_documents(args.source), sort_keys=True))
        return 0

    if args.command == "reindex-memory":
        print(json.dumps(agent.reindex_memory(), sort_keys=True))
        return 0

    for skill in agent.list_skills():
        print(f"{skill.name} {skill.version}")
    return 0


def console_main() -> None:
    raise SystemExit(main())
