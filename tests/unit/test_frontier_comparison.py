from pathlib import Path

import pytest

from agent.decisions.frontier_comparison import (
    assert_run_matches_gold,
    load_gold_tasks,
    task_record,
)


def test_load_gold_tasks_reads_frozen_file() -> None:
    root = Path(__file__).resolve().parents[1]
    tasks = load_gold_tasks(root / "test_data" / "router" / "tasks.json")
    assert [t["id"] for t in tasks] == ["plan", "easy"]
    assert tasks[0]["tier"] == "frontier"
    assert tasks[1]["tier"] == "small"


def test_task_record_sets_match() -> None:
    row = task_record(
        task_id="easy",
        prompt="Reply with the word pong.",
        gold_tier="small",
        logged_tier="small",
        reason="ok",
        confidence=0.9,
    )
    assert row["match"] is True
    assert row["logged_tier"] == "small"

    mismatch = task_record(
        task_id="easy",
        prompt="Reply with the word pong.",
        gold_tier="small",
        logged_tier="frontier",
        reason="wrong",
        confidence=0.5,
    )
    assert mismatch["match"] is False


def test_assert_run_matches_gold_passes_and_fails() -> None:
    gold = [
        {"id": "plan", "tier": "frontier", "prompt": "p"},
        {"id": "easy", "tier": "small", "prompt": "e"},
    ]
    good = {
        "tasks": [
            task_record(
                task_id="plan",
                prompt="p",
                gold_tier="frontier",
                logged_tier="frontier",
                reason="ok",
                confidence=None,
            ),
            task_record(
                task_id="easy",
                prompt="e",
                gold_tier="small",
                logged_tier="small",
                reason="ok",
                confidence=0.9,
            ),
        ]
    }
    assert_run_matches_gold(good, gold)

    bad = {
        "tasks": [
            task_record(
                task_id="plan",
                prompt="p",
                gold_tier="frontier",
                logged_tier="small",
                reason="ok",
                confidence=0.9,
            ),
            task_record(
                task_id="easy",
                prompt="e",
                gold_tier="small",
                logged_tier="small",
                reason="ok",
                confidence=0.9,
            ),
        ]
    }
    with pytest.raises(AssertionError, match="plan"):
        assert_run_matches_gold(bad, gold)


def _gold_pair() -> list[dict[str, str]]:
    return [
        {"id": "plan", "tier": "frontier", "prompt": "p"},
        {"id": "easy", "tier": "small", "prompt": "e"},
    ]


def _valid_run_tasks() -> list[dict[str, object]]:
    return [
        task_record(
            task_id="plan",
            prompt="p",
            gold_tier="frontier",
            logged_tier="frontier",
            reason="ok",
            confidence=None,
        ),
        task_record(
            task_id="easy",
            prompt="e",
            gold_tier="small",
            logged_tier="small",
            reason="ok",
            confidence=0.9,
        ),
    ]


def test_assert_run_matches_gold_rejects_duplicate_task_id() -> None:
    gold = _gold_pair()
    tasks = _valid_run_tasks()
    tasks.append(
        task_record(
            task_id="plan",
            prompt="p2",
            gold_tier="frontier",
            logged_tier="frontier",
            reason="dup",
            confidence=1.0,
        )
    )
    with pytest.raises(AssertionError, match="duplicate task id plan"):
        assert_run_matches_gold({"tasks": tasks}, gold)


def test_assert_run_matches_gold_rejects_missing_gold_id() -> None:
    gold = _gold_pair()
    tasks = [
        task_record(
            task_id="plan",
            prompt="p",
            gold_tier="frontier",
            logged_tier="frontier",
            reason="ok",
            confidence=None,
        ),
    ]
    with pytest.raises(AssertionError, match="missing task id easy"):
        assert_run_matches_gold({"tasks": tasks}, gold)


def test_assert_run_matches_gold_rejects_extra_run_id() -> None:
    gold = _gold_pair()
    tasks = _valid_run_tasks()
    tasks.append(
        task_record(
            task_id="extra",
            prompt="x",
            gold_tier="small",
            logged_tier="small",
            reason="extra",
            confidence=0.1,
        )
    )
    with pytest.raises(AssertionError, match="run has extra task ids"):
        assert_run_matches_gold({"tasks": tasks}, gold)


def test_assert_run_matches_gold_rejects_malformed_row() -> None:
    gold = _gold_pair()
    tasks = _valid_run_tasks()
    tasks[0] = "not-a-dict"  # type: ignore[assignment]
    with pytest.raises(AssertionError, match="each run task needs an id"):
        assert_run_matches_gold({"tasks": tasks}, gold)


def test_assert_run_matches_gold_rejects_gold_tier_field_mismatch() -> None:
    gold = _gold_pair()
    tasks = _valid_run_tasks()
    tasks[0] = task_record(
        task_id="plan",
        prompt="p",
        gold_tier="small",
        logged_tier="frontier",
        reason="ok",
        confidence=None,
    )
    with pytest.raises(AssertionError, match="gold_tier field != tasks.json"):
        assert_run_matches_gold({"tasks": tasks}, gold)
