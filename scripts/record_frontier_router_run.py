"""Opt-in live recording of model-router tiers for tests/test_data/router/tasks.json.

Requires HERMES_JEV_API_KEY. Does not call the generative model.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agent.decisions.frontier_comparison import load_gold_tasks, task_record  # noqa: E402
from agent.decisions.model_router import judge  # noqa: E402
from services.jev import JevClient  # noqa: E402
from utils.settings import load_settings  # noqa: E402

TASKS_PATH = ROOT / "tests" / "test_data" / "router" / "tasks.json"
OUT_PATH = ROOT / "tests" / "test_data" / "router" / "all-frontier-run.json"


def main() -> int:
    settings = load_settings()
    if not settings.jev_api_key:
        print("HERMES_JEV_API_KEY is required", file=sys.stderr)
        return 2
    client = JevClient(settings.jev_base_url, settings.jev_model, settings.jev_api_key)
    gold = load_gold_tasks(TASKS_PATH)
    rows: list[dict[str, object]] = []
    jev_model = settings.jev_model
    for task in gold:
        judgment = judge(client, task["prompt"])
        confidence = None
        tier_answer = judgment.answers.get("tier")
        if isinstance(tier_answer, dict):
            raw = tier_answer.get("confidence")
            if isinstance(raw, (int, float)) and not isinstance(raw, bool):
                confidence = float(raw)
        if judgment.model:
            jev_model = judgment.model
        rows.append(
            task_record(
                task_id=task["id"],
                prompt=task["prompt"],
                gold_tier=task["tier"],
                logged_tier=judgment.tier,
                reason=judgment.reason,
                confidence=confidence,
            )
        )
    payload = {
        "note": "All-frontier router comparison. Completions were not switched to a smaller model.",
        "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "jev_model": jev_model,
        "tasks": rows,
    }
    OUT_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    mismatches = [r["id"] for r in rows if not r["match"]]
    if mismatches:
        print(f"tier mismatch for: {mismatches}", file=sys.stderr)
        return 1
    print(f"wrote {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
