"""Command line interface for health checks, skill listing, autonomous agent runs, and collection maintenance."""

from __future__ import annotations

import argparse
import json
import sys

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
    subcommands.add_parser(
        "providers",
        help="Print model provider configuration and Gemini/OAuth readiness",
    )
    mem_list = subcommands.add_parser("memories", help="List stored memory keys")
    mem_list.add_argument("--prefix", default="", help="Optional key prefix filter")
    mem_put = subcommands.add_parser("remember", help="Store a memory record")
    mem_put.add_argument("key", help="Stable dotted memory key")
    mem_put.add_argument("value", help="Value text to store")
    mem_get = subcommands.add_parser("recall", help="Read a memory record by key")
    mem_get.add_argument("key", help="Memory key to read")
    args = parser.parse_args(argv)
    agent = HermesAgent(load_settings())

    if args.command == "health":
        report = agent.health()
        print(json.dumps(report, sort_keys=True))
        return 0

    if args.command == "providers":
        print(json.dumps(agent.provider_status(), sort_keys=True))
        return 0

    if args.command == "memories":
        print(json.dumps({"keys": agent.list_memories(args.prefix)}, sort_keys=True))
        return 0

    if args.command == "remember":
        stored = agent.remember(args.key, args.value)
        print(json.dumps({"key": args.key, "stored": stored}, sort_keys=True))
        return 0

    if args.command == "recall":
        try:
            print(agent.recall(args.key))
            return 0
        except FileNotFoundError:
            print("No record is stored for that key.", file=sys.stderr)
            return 1

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
