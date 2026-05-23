from __future__ import annotations

from typing import Any

from pytest import MonkeyPatch

from config import config
from execution import rebalance_orchestrator as orchestrator
from execution.rebalance_orchestrator import (
    build_last_close_prices_for_symbols,
    get_symbols_for_rebalance,
    run_rebalance,
    should_prepare_leverage,
)


class FakeClient:
    """Placeholder client used only for monkeypatched orchestrator tests."""


def _candles(close: float | None) -> list[dict[str, Any]]:
    if close is None:
        return []
    return [{"start_time_ms": 1, "close": close}]


def _patch_base_run_dependencies(
    monkeypatch: MonkeyPatch,
    current_positions: dict[str, float],
    prices: dict[str, float],
) -> dict[str, Any]:
    calls: dict[str, Any] = {
        "cancel": [],
        "execute": [],
        "cleanup": [],
        "positions": 0,
    }

    monkeypatch.setattr(orchestrator, "get_exchange_equity", lambda client: 10.0)
    monkeypatch.setattr(orchestrator, "get_total_equity", lambda exchange_equity: 100.0)

    def fake_get_current_positions(client: FakeClient) -> dict[str, float]:
        calls["positions"] += 1
        return dict(current_positions)

    def fake_get_hourly_candles(client: FakeClient, symbol: str, limit: int) -> list[dict[str, Any]]:
        return _candles(prices.get(symbol))

    def fake_cancel_all_orders_for_symbol(client: FakeClient, symbol: str) -> dict[str, Any]:
        calls["cancel"].append(symbol)
        return {"ok": True}

    def fake_rebalance_by_limit_order(
        client: FakeClient,
        symbol: str,
        qty_delta: float,
        prepare_leverage: bool = True,
    ) -> dict[str, Any]:
        calls["execute"].append(
            {
                "symbol": symbol,
                "qty_delta": qty_delta,
                "prepare_leverage": prepare_leverage,
            }
        )
        return {"status": "completed", "symbol": symbol}

    def fake_cleanup_small_positions(
        client: FakeClient,
        current_positions: dict[str, float],
        last_close_prices: dict[str, float],
    ) -> dict[str, Any]:
        calls["cleanup"].append(
            {
                "current_positions": current_positions,
                "last_close_prices": last_close_prices,
            }
        )
        return {"closed": [], "failed": [], "skipped": []}

    monkeypatch.setattr(orchestrator, "get_current_positions", fake_get_current_positions)
    monkeypatch.setattr(orchestrator, "get_hourly_candles", fake_get_hourly_candles)
    monkeypatch.setattr(orchestrator, "cancel_all_orders_for_symbol", fake_cancel_all_orders_for_symbol)
    monkeypatch.setattr(orchestrator, "rebalance_by_limit_order", fake_rebalance_by_limit_order)
    monkeypatch.setattr(orchestrator, "cleanup_small_positions", fake_cleanup_small_positions)
    monkeypatch.setattr(config, "RESERVE_BALANCE_USDT", 40.0)
    monkeypatch.setattr(config, "MIN_ORDER_NOTIONAL_USDT", 5.0)
    monkeypatch.setattr(config, "ENABLE_SMALL_POSITION_CLEANUP", 0)
    return calls


def test_get_symbols_for_rebalance_returns_union() -> None:
    result = get_symbols_for_rebalance(
        current_positions={"BTCUSDT": 0.01},
        target_leverage={"ETHUSDT": 1.0},
    )

    assert result == ["BTCUSDT", "ETHUSDT"]


def test_should_prepare_leverage_true_for_opening_new_exposure() -> None:
    assert should_prepare_leverage(0.0, 1.0) is True


def test_should_prepare_leverage_true_for_increasing_exposure() -> None:
    assert should_prepare_leverage(1.0, 2.0) is True


def test_should_prepare_leverage_false_for_reducing_exposure() -> None:
    assert should_prepare_leverage(2.0, 1.0) is False


def test_should_prepare_leverage_false_for_closing_exposure() -> None:
    assert should_prepare_leverage(1.0, 0.0) is False


def test_should_prepare_leverage_flip_larger_target_abs_true() -> None:
    assert should_prepare_leverage(1.0, -2.0) is True


def test_should_prepare_leverage_flip_smaller_or_equal_target_abs_false() -> None:
    assert should_prepare_leverage(2.0, -1.0) is False
    assert should_prepare_leverage(2.0, -2.0) is False


def test_build_last_close_prices_for_symbols_returns_prices(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(orchestrator, "get_hourly_candles", lambda client, symbol, limit: _candles(12.5))

    result = build_last_close_prices_for_symbols(FakeClient(), ["BTCUSDT"])

    assert result == {"BTCUSDT": 12.5}


def test_build_last_close_prices_for_symbols_skips_symbols_without_valid_close(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(orchestrator, "get_hourly_candles", lambda client, symbol, limit: _candles(None))

    result = build_last_close_prices_for_symbols(FakeClient(), ["BTCUSDT"])

    assert result == {}


def test_run_rebalance_returns_no_action_for_empty_current_and_target(
    monkeypatch: MonkeyPatch,
) -> None:
    calls = _patch_base_run_dependencies(monkeypatch, current_positions={}, prices={})

    result = run_rebalance(FakeClient(), {})

    assert result["status"] == "no_action"
    assert result["delta_qty"] == {}
    assert calls["cancel"] == []
    assert calls["execute"] == []


def test_run_rebalance_builds_plan_and_calls_rebalancer_for_nonzero_deltas(
    monkeypatch: MonkeyPatch,
) -> None:
    calls = _patch_base_run_dependencies(monkeypatch, current_positions={}, prices={"DOGEUSDT": 10.0})

    result = run_rebalance(FakeClient(), {"DOGEUSDT": 1.0})

    assert result["status"] == "completed"
    assert result["target_positions"] == {"DOGEUSDT": 10.0}
    assert result["delta_qty"] == {"DOGEUSDT": 10.0}
    assert calls["execute"] == [{"symbol": "DOGEUSDT", "qty_delta": 10.0, "prepare_leverage": True}]


def test_run_rebalance_does_not_call_rebalancer_for_zero_deltas(
    monkeypatch: MonkeyPatch,
) -> None:
    calls = _patch_base_run_dependencies(
        monkeypatch,
        current_positions={"DOGEUSDT": 10.0},
        prices={"DOGEUSDT": 10.0},
    )

    result = run_rebalance(FakeClient(), {"DOGEUSDT": 1.0})

    assert result["status"] == "no_action"
    assert result["delta_qty"] == {"DOGEUSDT": 0.0}
    assert calls["execute"] == []


def test_run_rebalance_passes_prepare_leverage_false_when_closing(
    monkeypatch: MonkeyPatch,
) -> None:
    calls = _patch_base_run_dependencies(
        monkeypatch,
        current_positions={"DOGEUSDT": 10.0},
        prices={"DOGEUSDT": 10.0},
    )

    run_rebalance(FakeClient(), {})

    assert calls["execute"] == [{"symbol": "DOGEUSDT", "qty_delta": -10.0, "prepare_leverage": False}]


def test_run_rebalance_passes_prepare_leverage_true_when_opening(
    monkeypatch: MonkeyPatch,
) -> None:
    calls = _patch_base_run_dependencies(monkeypatch, current_positions={}, prices={"DOGEUSDT": 10.0})

    run_rebalance(FakeClient(), {"DOGEUSDT": 1.0})

    assert calls["execute"][0]["prepare_leverage"] is True


def test_run_rebalance_returns_partial_failed_if_one_symbol_execution_fails(
    monkeypatch: MonkeyPatch,
) -> None:
    _patch_base_run_dependencies(
        monkeypatch,
        current_positions={},
        prices={"BTCUSDT": 10.0, "ETHUSDT": 10.0},
    )

    def fake_rebalance_by_limit_order(
        client: FakeClient,
        symbol: str,
        qty_delta: float,
        prepare_leverage: bool = True,
    ) -> dict[str, Any]:
        if symbol == "BTCUSDT":
            raise RuntimeError("boom")
        return {"status": "completed", "symbol": symbol}

    monkeypatch.setattr(orchestrator, "rebalance_by_limit_order", fake_rebalance_by_limit_order)

    result = run_rebalance(FakeClient(), {"BTCUSDT": 1.0, "ETHUSDT": 1.0})

    assert result["status"] == "partial_failed"
    assert result["execution_results"]["BTCUSDT"]["status"] == "failed"
    assert result["execution_results"]["ETHUSDT"]["status"] == "completed"


def test_run_rebalance_calls_cleanup_small_positions_if_enabled(
    monkeypatch: MonkeyPatch,
) -> None:
    calls = _patch_base_run_dependencies(monkeypatch, current_positions={}, prices={"DOGEUSDT": 10.0})
    monkeypatch.setattr(config, "ENABLE_SMALL_POSITION_CLEANUP", 1)

    result = run_rebalance(FakeClient(), {"DOGEUSDT": 1.0})

    assert result["cleanup_result"] == {"closed": [], "failed": [], "skipped": []}
    assert len(calls["cleanup"]) == 1


def test_run_rebalance_skips_cleanup_if_disabled(monkeypatch: MonkeyPatch) -> None:
    calls = _patch_base_run_dependencies(monkeypatch, current_positions={}, prices={"DOGEUSDT": 10.0})
    monkeypatch.setattr(config, "ENABLE_SMALL_POSITION_CLEANUP", 0)

    result = run_rebalance(FakeClient(), {"DOGEUSDT": 1.0})

    assert result["cleanup_result"] is None
    assert calls["cleanup"] == []


def test_run_rebalance_cancels_all_orders_before_and_after_execution(
    monkeypatch: MonkeyPatch,
) -> None:
    calls = _patch_base_run_dependencies(monkeypatch, current_positions={}, prices={"DOGEUSDT": 10.0})

    run_rebalance(FakeClient(), {"DOGEUSDT": 1.0})

    assert calls["cancel"] == ["DOGEUSDT", "DOGEUSDT"]
