"""Equity-based rebalance trigger helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from config import config


def calculate_equity_change_pct(
    current_equity: float,
    reference_equity: float,
) -> float:
    """Return relative equity change from a reference equity value."""
    if reference_equity <= 0:
        return 0.0
    return current_equity / reference_equity - 1


def should_rebalance(
    current_equity: float,
    reference_equity: float,
    threshold_pct: float | None = None,
) -> bool:
    """Return True when absolute equity change reaches the threshold."""
    if reference_equity <= 0:
        return False

    threshold = float(config.REBALANCE_THRESHOLD_PCT if threshold_pct is None else threshold_pct)
    change_pct = calculate_equity_change_pct(current_equity, reference_equity)
    return abs(change_pct) >= threshold


def initialize_rebalance_equity_if_needed(
    state: dict[str, Any],
    current_equity: float,
) -> dict[str, Any]:
    """Initialize rebalance_equity in state if it is missing or invalid."""
    updated_state = dict(state)
    rebalance_equity = _to_float(updated_state.get("rebalance_equity"))
    if rebalance_equity is None or rebalance_equity <= 0:
        updated_state["rebalance_equity"] = float(current_equity)
    return updated_state


def record_successful_rebalance(
    state: dict[str, Any],
    new_rebalance_equity: float,
    selected_symbol: str | None = None,
) -> dict[str, Any]:
    """Record successful rebalance fields in runtime state."""
    updated_state = dict(state)
    timestamp = _utc_timestamp()
    timestamps = updated_state.get("rebalance_timestamps")
    if not isinstance(timestamps, list):
        timestamps = []
    timestamps.append(timestamp)

    previous_max = _to_float(updated_state.get("max_total_equity_seen"))
    updated_state["rebalance_equity"] = float(new_rebalance_equity)
    updated_state["last_rebalance_timestamp"] = timestamp
    updated_state["rebalance_timestamps"] = timestamps
    updated_state["last_selected_symbol"] = selected_symbol
    updated_state["max_total_equity_seen"] = (
        float(new_rebalance_equity)
        if previous_max is None
        else max(previous_max, float(new_rebalance_equity))
    )
    updated_state["last_error"] = None
    return updated_state


def _utc_timestamp() -> str:
    """Return an ISO-formatted UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def _to_float(value: Any) -> float | None:
    """Convert a value to float without raising."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
