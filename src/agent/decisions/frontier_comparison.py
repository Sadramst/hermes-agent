from __future__ import annotations

import json
from pathlib import Path


def load_gold_tasks(path: Path) -> list[dict[str, str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    tasks = data["tasks"]
    out: list[dict[str, str]] = []
    for item in tasks:
        out.append(
            {
                "id": str(item["id"]),
                "tier": str(item["tier"]),
                "prompt": str(item["prompt"]),
            }
        )
    return out


def task_record(
    *,
    task_id: str,
    prompt: str,
    gold_tier: str,
    logged_tier: str,
    reason: str,
    confidence: float | None,
) -> dict[str, object]:
    return {
        "id": task_id,
        "prompt": prompt,
        "gold_tier": gold_tier,
        "logged_tier": logged_tier,
        "reason": reason,
        "confidence": confidence,
        "match": logged_tier == gold_tier,
    }


def assert_run_matches_gold(run: dict[str, object], gold_tasks: list[dict[str, str]]) -> None:
    raw = run.get("tasks")
    if not isinstance(raw, list):
        raise AssertionError("run.tasks must be a list")
    by_id: dict[str, dict[str, object]] = {}
    for row in raw:
        if not isinstance(row, dict) or "id" not in row:
            raise AssertionError("each run task needs an id")
        tid = str(row["id"])
        if tid in by_id:
            raise AssertionError(f"duplicate task id {tid}")
        by_id[tid] = row
    for gold in gold_tasks:
        tid = gold["id"]
        if tid not in by_id:
            raise AssertionError(f"missing task id {tid}")
        row = by_id[tid]
        logged = str(row.get("logged_tier"))
        gold_tier = gold["tier"]
        if logged != gold_tier:
            raise AssertionError(f"{tid}: logged_tier {logged!r} != gold {gold_tier!r}")
        if str(row.get("gold_tier")) != gold_tier:
            raise AssertionError(f"{tid}: gold_tier field != tasks.json")
    if len(by_id) != len(gold_tasks):
        raise AssertionError("run has extra task ids")
