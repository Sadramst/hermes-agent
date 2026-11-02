# tests/unit/test_frontier_run_artifact.py
import json
from pathlib import Path

from agent.decisions.frontier_comparison import assert_run_matches_gold, load_gold_tasks

ROOT = Path(__file__).resolve().parents[1]
GOLD = ROOT / "test_data" / "router" / "tasks.json"
RUN = ROOT / "test_data" / "router" / "all-frontier-run.json"


def test_committed_all_frontier_run_matches_gold_tiers() -> None:
    gold = load_gold_tasks(GOLD)
    run = json.loads(RUN.read_text(encoding="utf-8"))
    assert_run_matches_gold(run, gold)
