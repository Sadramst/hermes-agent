"""Audit record for one Jev decision. Field names only. Never the API key."""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger("hermes.jev")


def audit_decision(
    *,
    pack: str,
    pack_version: str,
    mode: str,
    model: str,
    state_fields: list[str],
    answers: dict[str, Any],
    proposed: str,
    effective: str,
    comparison: dict[str, object] | None = None,
) -> dict[str, object]:
    """Log the distribution and the outcome code chose. Omit state values."""
    record: dict[str, object] = {
        "pack": pack,
        "pack_version": pack_version,
        "mode": mode,
        "model": model,
        "state_fields": list(state_fields),
        "answers": answers,
        "proposed": proposed,
        "effective": effective,
    }
    suggested = ""
    reason = ""
    index_text = ""
    in_prompt = ""
    match_text = ""
    shown_text = ""
    filtered = ""
    route_text = ""
    side_text = ""
    enforced = ""
    kind_text = ""
    memory_key = ""
    persisted = ""
    call_text = ""
    tool_text = ""
    statuses_text = ""
    tier_text = ""
    looping_text = ""
    done_text = ""
    if comparison is not None:
        stored = dict(comparison)
        index = stored.get("hermes_index")
        if isinstance(index, list):
            stored["hermes_index"] = list(index)
            index_text = ",".join(name for name in index if isinstance(name, str))
        match_ids = stored.get("match_ids")
        if isinstance(match_ids, list):
            stored["match_ids"] = list(match_ids)
            match_text = ",".join(name for name in match_ids if isinstance(name, str))
        shown_ids = stored.get("shown")
        if isinstance(shown_ids, list):
            stored["shown"] = list(shown_ids)
            shown_text = ",".join(name for name in shown_ids if isinstance(name, str))
        record["comparison"] = stored
        suggested_value = stored.get("suggested", "")
        reason_value = stored.get("reason", "")
        suggested = suggested_value if isinstance(suggested_value, str) else ""
        reason = reason_value if isinstance(reason_value, str) else ""
        flag = stored.get("suggestion_in_prompt")
        if flag is False:
            in_prompt = "false"
        elif flag is True:
            in_prompt = "true"
        filtered_flag = stored.get("filtered")
        if filtered_flag is False:
            filtered = "false"
        elif filtered_flag is True:
            filtered = "true"
        route_value = stored.get("route")
        if isinstance(route_value, str):
            route_text = route_value
        side_value = stored.get("side")
        if isinstance(side_value, str):
            side_text = side_value
        enforced_flag = stored.get("enforced")
        if enforced_flag is False:
            enforced = "false"
        elif enforced_flag is True:
            enforced = "true"
        kind_value = stored.get("kind")
        if isinstance(kind_value, str):
            kind_text = kind_value
        key_value = stored.get("memory_key")
        if isinstance(key_value, str):
            memory_key = key_value
        persisted_flag = stored.get("persisted")
        if persisted_flag is False:
            persisted = "false"
        elif persisted_flag is True:
            persisted = "true"
        call_names = stored.get("call_names")
        if isinstance(call_names, list):
            stored["call_names"] = list(call_names)
            call_text = ",".join(name for name in call_names if isinstance(name, str))
        tool_value = stored.get("tool")
        if isinstance(tool_value, str):
            tool_text = tool_value
        statuses = stored.get("statuses")
        if isinstance(statuses, list):
            stored["statuses"] = list(statuses)
            statuses_text = ",".join(name for name in statuses if isinstance(name, str))
        tier_value = stored.get("tier")
        if isinstance(tier_value, str):
            tier_text = tier_value
        looping_flag = stored.get("looping")
        if looping_flag is False:
            looping_text = "false"
        elif looping_flag is True:
            looping_text = "true"
        done_flag = stored.get("done")
        if done_flag is False:
            done_text = "false"
        elif done_flag is True:
            done_text = "true"
    logger.info(
        "jev.decision pack=%s version=%s mode=%s model=%s proposed=%s effective=%s "
        "fields=%s suggested=%s reason=%s hermes_index=%s suggestion_in_prompt=%s "
        "matches=%s shown=%s filtered=%s route=%s side=%s enforced=%s "
        "kind=%s memory_key=%s persisted=%s calls=%s tool=%s statuses=%s tier=%s "
        "looping=%s done=%s answers=%s",
        pack,
        pack_version,
        mode,
        model,
        proposed,
        effective,
        ",".join(state_fields),
        suggested,
        reason,
        index_text,
        in_prompt,
        match_text,
        shown_text,
        filtered,
        route_text,
        side_text,
        enforced,
        kind_text,
        memory_key,
        persisted,
        call_text,
        tool_text,
        statuses_text,
        tier_text,
        looping_text,
        done_text,
        _answers_text(answers),
    )
    return record


def _answers_text(answers: dict[str, Any]) -> str:
    try:
        return json.dumps(answers, sort_keys=True, separators=(",", ":"), default=str)
    except (TypeError, ValueError):
        return ""
