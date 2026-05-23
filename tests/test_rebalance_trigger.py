from __future__ import annotations

import pytest

from triggers.rebalance_trigger import (
    calculate_equity_change_pct,
    initialize_rebalance_equity_if_needed,
    record_successful_rebalance,
    should_rebalance,
)


def test_calculate_equity_change_pct_positive_change() -> None:
    assert calculate_equity_change_pct(110.0, 100.0) == pytest.approx(0.1)


def test_calculate_equity_change_pct_negative_change() -> None:
    assert calculate_equity_change_pct(90.0, 100.0) == pytest.approx(-0.1)


def test_should_rebalance_true_for_positive_threshold() -> None:
    assert should_rebalance(105.0, 100.0, threshold_pct=0.05) is True


def test_should_rebalance_true_for_negative_threshold() -> None:
    assert should_rebalance(95.0, 100.0, threshold_pct=0.05) is True


def test_should_rebalance_false_below_threshold() -> None:
    assert should_rebalance(104.9, 100.0, threshold_pct=0.05) is False


def test_initialize_rebalance_equity_if_needed_sets_missing_value() -> None:
    state = initialize_rebalance_equity_if_needed({"rebalance_equity": None}, 123.0)

    assert state["rebalance_equity"] == 123.0


def test_initialize_rebalance_equity_if_needed_preserves_existing_value() -> None:
    state = initialize_rebalance_equity_if_needed({"rebalance_equity": 100.0}, 123.0)

    assert state["rebalance_equity"] == 100.0


def test_record_successful_rebalance_updates_required_state_fields() -> None:
    state = record_successful_rebalance(
        {
            "rebalance_timestamps": [],
            "max_total_equity_seen": 90.0,
            "last_error": "old",
        },
        new_rebalance_equity=100.0,
        selected_symbol="BTCUSDT",
    )

    assert state["rebalance_equity"] == 100.0
    assert isinstance(state["last_rebalance_timestamp"], str)
    assert len(state["rebalance_timestamps"]) == 1
    assert state["last_selected_symbol"] == "BTCUSDT"
    assert state["max_total_equity_seen"] == 100.0
    assert state["last_error"] is None
