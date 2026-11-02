"""Command line interface for health checks, skill listing, autonomous agent runs, and collection maintenance."""

from __future__ import annotations

import argparse
import json

from agent.core import HermesAgent
from agent.tools import MAX_STEPS
from utils.settings import load_settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hermes")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("health", help="Print the agent health report as JSON")
    subcommands.add_parser("skills", help="List skills from the skills directory")
    run_cmd = subcommands.add_parser(
        "run",
        help="Run the autonomous multi-step tool-calling agent loop for a prompt",
    )
    run_cmd.add_argument("prompt", help="Prompt or task for Hermes Agent")
    run_cmd.add_argument(
        "--max-steps",
        dest="max_steps",
        type=int,
        default=MAX_STEPS,
        help="Maximum autonomous tool-calling iterations (default: 4)",
    )
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

    if args.command == "run":
        print(json.dumps(agent.run_agent(args.prompt, max_steps=args.max_steps), sort_keys=True))
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
