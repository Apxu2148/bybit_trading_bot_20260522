from __future__ import annotations

import pytest
from pytest import MonkeyPatch

from config import config
from portfolio.rebalance_plan import (
    align_position_keys,
    build_rebalance_plan,
    calculate_delta_qty,
    calculate_target_positions,
)


def test_calculate_target_positions_converts_positive_leverage_to_positive_qty() -> None:
    result = calculate_target_positions(
        target_leverage={"BTCUSDT": 1.0},
        total_equity=100.0,
        last_close_prices={"BTCUSDT": 20_000.0},
    )

    assert result == {"BTCUSDT": 0.005}


def test_calculate_target_positions_converts_negative_leverage_to_negative_qty() -> None:
    result = calculate_target_positions(
        target_leverage={"ETHUSDT": -2.0},
        total_equity=100.0,
        last_close_prices={"ETHUSDT": 2_000.0},
    )

    assert result == {"ETHUSDT": -0.1}


def test_calculate_target_positions_skips_missing_price() -> None:
    result = calculate_target_positions(
        target_leverage={"BTCUSDT": 1.0},
        total_equity=100.0,
        last_close_prices={},
    )

    assert result == {}


def test_align_position_keys_aligns_different_symbol_sets() -> None:
    current_aligned, target_aligned = align_position_keys(
        current_positions={"SOLUSDT": 100.0},
        target_positions={"BTCUSDT": 0.01},
    )

    assert current_aligned == {"BTCUSDT": 0.0, "SOLUSDT": 100.0}
    assert target_aligned == {"BTCUSDT": 0.01, "SOLUSDT": 0.0}


def test_calculate_delta_qty_computes_open_new_position(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(config, "MIN_ORDER_NOTIONAL_USDT", 5.0)

    result = calculate_delta_qty(
        current_positions={},
        target_positions={"BTCUSDT": 0.01},
        last_close_prices={"BTCUSDT": 20_000.0},
    )

    assert result == {"BTCUSDT": 0.01}


def test_calculate_delta_qty_computes_close_old_position(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(config, "MIN_ORDER_NOTIONAL_USDT", 5.0)

    result = calculate_delta_qty(
        current_positions={"BTCUSDT": 0.01},
        target_positions={},
        last_close_prices={"BTCUSDT": 20_000.0},
    )

    assert result == {"BTCUSDT": -0.01}


def test_calculate_delta_qty_computes_position_flip(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(config, "MIN_ORDER_NOTIONAL_USDT", 5.0)

    result = calculate_delta_qty(
        current_positions={"BTCUSDT": 0.01},
        target_positions={"BTCUSDT": -0.02},
        last_close_prices={"BTCUSDT": 20_000.0},
    )

    assert result == {"BTCUSDT": pytest.approx(-0.03)}


def test_calculate_delta_qty_sets_small_notional_delta_to_zero(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(config, "MIN_ORDER_NOTIONAL_USDT", 5.0)

    result = calculate_delta_qty(
        current_positions={},
        target_positions={"BTCUSDT": 0.0001},
        last_close_prices={"BTCUSDT": 20_000.0},
    )

    assert result == {"BTCUSDT": 0.0}


def test_calculate_delta_qty_keeps_delta_if_notional_meets_minimum(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(config, "MIN_ORDER_NOTIONAL_USDT", 5.0)

    result = calculate_delta_qty(
        current_positions={},
        target_positions={"BTCUSDT": 0.00025},
        last_close_prices={"BTCUSDT": 20_000.0},
    )

    assert result == {"BTCUSDT": 0.00025}


def test_build_rebalance_plan_returns_all_required_keys(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(config, "MIN_ORDER_NOTIONAL_USDT", 5.0)

    result = build_rebalance_plan(
        current_positions={},
        target_leverage={"BTCUSDT": 1.0},
        total_equity=100.0,
        last_close_prices={"BTCUSDT": 20_000.0},
    )

    assert set(result) == {
        "target_positions",
        "current_positions_aligned",
        "target_positions_aligned",
        "delta_qty",
    }
    assert result["target_positions"] == {"BTCUSDT": 0.005}
    assert result["delta_qty"] == {"BTCUSDT": 0.005}


def test_build_rebalance_plan_empty_target_closes_existing_large_position(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "MIN_ORDER_NOTIONAL_USDT", 5.0)

    result = build_rebalance_plan(
        current_positions={"BTCUSDT": 0.01},
        target_leverage={},
        total_equity=100.0,
        last_close_prices={"BTCUSDT": 20_000.0},
    )

    assert result["target_positions"] == {}
    assert result["current_positions_aligned"] == {"BTCUSDT": 0.01}
    assert result["target_positions_aligned"] == {"BTCUSDT": 0.0}
    assert result["delta_qty"] == {"BTCUSDT": -0.01}


def test_build_rebalance_plan_handles_empty_current_and_empty_target() -> None:
    result = build_rebalance_plan(
        current_positions={},
        target_leverage={},
        total_equity=100.0,
        last_close_prices={},
    )

    assert result == {
        "target_positions": {},
        "current_positions_aligned": {},
        "target_positions_aligned": {},
        "delta_qty": {},
    }
