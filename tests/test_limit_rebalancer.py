from __future__ import annotations

from typing import Any

import pytest
from pytest import MonkeyPatch

from config import config
from execution import limit_rebalancer as rebalancer
from execution.limit_rebalancer import (
    RebalanceAlreadyActiveError,
    calculate_remaining_delta,
    calculate_simple_ma,
    calculate_target_position_qty,
    extract_tick_size_and_qty_step,
    get_latest_close,
    is_rebalance_complete,
    rebalance_by_limit_order,
    should_place_limit_order,
)


class FakeClient:
    """Placeholder client used only for monkeypatched rebalancer tests."""


def _candles(closes: list[float]) -> list[dict[str, Any]]:
    return [{"close": close, "start_time_ms": index * 60_000} for index, close in enumerate(closes)]


def _patch_common_rebalancer_dependencies(monkeypatch: MonkeyPatch, positions: list[float]) -> dict[str, Any]:
    calls: dict[str, Any] = {
        "cancel": [],
        "orders": [],
        "sleep": 0,
        "margin": 0,
        "leverage": 0,
    }
    position_values = list(positions)

    def fake_get_current_positions(client: FakeClient, symbols: list[str] | None = None) -> dict[str, float]:
        value = position_values.pop(0) if position_values else positions[-1]
        return {"DOGEUSDT": value} if value != 0 else {}

    def fake_cancel_all_orders_for_symbol(client: FakeClient, symbol: str) -> dict[str, Any]:
        calls["cancel"].append(symbol)
        return {"ok": True}

    def fake_place_limit_order(
        client: FakeClient,
        symbol: str,
        qty: float,
        price: float,
        reduce_only: bool = False,
    ) -> dict[str, Any]:
        calls["orders"].append(
            {
                "symbol": symbol,
                "qty": qty,
                "price": price,
                "reduce_only": reduce_only,
            }
        )
        return {"ok": True}

    def fake_try_set_cross_margin_if_possible(client: FakeClient, symbol: str) -> bool:
        calls["margin"] += 1
        return True

    def fake_try_set_leverage_from_candidates(client: FakeClient, symbol: str) -> int:
        calls["leverage"] += 1
        return 5

    monkeypatch.setattr(rebalancer, "get_current_positions", fake_get_current_positions)
    monkeypatch.setattr(rebalancer, "cancel_all_orders_for_symbol", fake_cancel_all_orders_for_symbol)
    monkeypatch.setattr(rebalancer, "place_limit_order", fake_place_limit_order)
    monkeypatch.setattr(
        rebalancer,
        "get_instrument_info",
        lambda client, symbol: {
            "priceFilter": {"tickSize": "0.1"},
            "lotSizeFilter": {"qtyStep": "0.1"},
        },
    )
    monkeypatch.setattr(rebalancer, "try_set_cross_margin_if_possible", fake_try_set_cross_margin_if_possible)
    monkeypatch.setattr(rebalancer, "try_set_leverage_from_candidates", fake_try_set_leverage_from_candidates)
    monkeypatch.setattr(rebalancer, "_sleep", lambda seconds: calls.__setitem__("sleep", calls["sleep"] + 1))
    monkeypatch.setattr(config, "LIMIT_MA_PERIOD_MINUTES", 3)
    monkeypatch.setattr(config, "LIMIT_MA_EXTRA_CANDLES", 2)
    monkeypatch.setattr(config, "LIMIT_ORDER_CHECK_INTERVAL_SECONDS", 0)
    monkeypatch.setattr(config, "ENABLE_MAX_REBALANCE_DURATION", 0)
    monkeypatch.setattr(config, "MAX_REBALANCE_DURATION_SECONDS", 100)
    monkeypatch.setattr(config, "MIN_ORDER_NOTIONAL_USDT", 5.0)
    rebalancer.ACTIVE_REBALANCE_SYMBOLS.clear()
    return calls


def test_calculate_simple_ma_returns_correct_ma() -> None:
    assert calculate_simple_ma(_candles([1.0, 2.0, 3.0, 4.0]), 3) == pytest.approx(3.0)


def test_extract_tick_size_and_qty_step_parses_nested_bybit_metadata() -> None:
    instrument_info = {
        "priceFilter": {"tickSize": "0.00001"},
        "lotSizeFilter": {"qtyStep": "1"},
    }

    assert extract_tick_size_and_qty_step(instrument_info) == (0.00001, 1.0)


def test_extract_tick_size_and_qty_step_raises_when_tick_size_missing() -> None:
    instrument_info = {"priceFilter": {}, "lotSizeFilter": {"qtyStep": "1"}}

    with pytest.raises(ValueError, match="priceFilter.tickSize"):
        extract_tick_size_and_qty_step(instrument_info)


def test_extract_tick_size_and_qty_step_raises_when_qty_step_missing() -> None:
    instrument_info = {"priceFilter": {"tickSize": "0.00001"}, "lotSizeFilter": {}}

    with pytest.raises(ValueError, match="lotSizeFilter.qtyStep"):
        extract_tick_size_and_qty_step(instrument_info)


def test_calculate_simple_ma_returns_none_if_not_enough_candles() -> None:
    assert calculate_simple_ma(_candles([1.0, 2.0]), 3) is None


def test_get_latest_close_returns_last_close() -> None:
    assert get_latest_close(_candles([1.0, 2.0, 3.0])) == 3.0


def test_should_place_limit_order_returns_true_for_buy_when_close_above_ma() -> None:
    assert should_place_limit_order(1.0, latest_close=11.0, ma_value=10.0) is True


def test_should_place_limit_order_returns_false_for_buy_when_close_at_or_below_ma() -> None:
    assert should_place_limit_order(1.0, latest_close=10.0, ma_value=10.0) is False
    assert should_place_limit_order(1.0, latest_close=9.0, ma_value=10.0) is False


def test_should_place_limit_order_returns_true_for_sell_when_close_below_ma() -> None:
    assert should_place_limit_order(-1.0, latest_close=9.0, ma_value=10.0) is True


def test_should_place_limit_order_returns_false_for_sell_when_close_at_or_above_ma() -> None:
    assert should_place_limit_order(-1.0, latest_close=10.0, ma_value=10.0) is False
    assert should_place_limit_order(-1.0, latest_close=11.0, ma_value=10.0) is False


def test_calculate_target_position_qty_works() -> None:
    assert calculate_target_position_qty(2.0, -0.5) == 1.5


def test_calculate_remaining_delta_works() -> None:
    assert calculate_remaining_delta(1.0, 3.0) == 2.0


def test_is_rebalance_complete_true_when_notional_below_minimum(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(config, "MIN_ORDER_NOTIONAL_USDT", 5.0)

    assert is_rebalance_complete(remaining_delta=0.1, last_close_price=40.0) is True


def test_is_rebalance_complete_false_when_notional_meets_minimum(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(config, "MIN_ORDER_NOTIONAL_USDT", 5.0)

    assert is_rebalance_complete(remaining_delta=0.1, last_close_price=50.0) is False


def test_rebalance_by_limit_order_returns_completed_immediately_for_zero_qty() -> None:
    result = rebalance_by_limit_order(FakeClient(), "DOGEUSDT", 0.0)

    assert result["status"] == "completed"
    assert result["orders_placed"] == 0


def test_rebalance_by_limit_order_rejects_same_symbol_concurrent_active_rebalance() -> None:
    rebalancer.ACTIVE_REBALANCE_SYMBOLS.add("DOGEUSDT")

    with pytest.raises(RebalanceAlreadyActiveError):
        rebalance_by_limit_order(FakeClient(), "DOGEUSDT", 1.0)

    rebalancer.ACTIVE_REBALANCE_SYMBOLS.clear()


def test_rebalance_by_limit_order_cancels_orders_before_starting(monkeypatch: MonkeyPatch) -> None:
    calls = _patch_common_rebalancer_dependencies(monkeypatch, positions=[0.0, 1.0])
    monkeypatch.setattr(rebalancer, "get_minute_candles", lambda client, symbol, limit: _candles([10.0, 10.0, 10.0]))

    result = rebalance_by_limit_order(FakeClient(), "DOGEUSDT", 1.0)

    assert result["status"] == "completed"
    assert calls["cancel"][0] == "DOGEUSDT"


def test_rebalance_by_limit_order_places_limit_order_when_condition_is_met(
    monkeypatch: MonkeyPatch,
) -> None:
    calls = _patch_common_rebalancer_dependencies(monkeypatch, positions=[0.0, 0.0, 1.0])
    monkeypatch.setattr(rebalancer, "get_minute_candles", lambda client, symbol, limit: _candles([8.0, 10.0, 12.0]))

    result = rebalance_by_limit_order(FakeClient(), "DOGEUSDT", 1.0)

    assert result["status"] == "completed"
    assert calls["orders"] == [
        {
            "symbol": "DOGEUSDT",
            "qty": 1.0,
            "price": 10.0,
            "reduce_only": False,
        }
    ]


def test_rebalance_by_limit_order_does_not_place_order_when_condition_is_not_met(
    monkeypatch: MonkeyPatch,
) -> None:
    calls = _patch_common_rebalancer_dependencies(monkeypatch, positions=[0.0, 0.0, 0.0])
    times = iter([0.0, 0.0, 2.0])
    monkeypatch.setattr(rebalancer, "_now_seconds", lambda: next(times))
    monkeypatch.setattr(config, "ENABLE_MAX_REBALANCE_DURATION", 1)
    monkeypatch.setattr(config, "MAX_REBALANCE_DURATION_SECONDS", 1)
    monkeypatch.setattr(rebalancer, "get_minute_candles", lambda client, symbol, limit: _candles([12.0, 10.0, 8.0]))

    result = rebalance_by_limit_order(FakeClient(), "DOGEUSDT", 1.0)

    assert result["status"] == "timeout"
    assert calls["orders"] == []


def test_rebalance_by_limit_order_cancels_orders_after_iteration(monkeypatch: MonkeyPatch) -> None:
    calls = _patch_common_rebalancer_dependencies(monkeypatch, positions=[0.0, 0.0, 1.0])
    monkeypatch.setattr(rebalancer, "get_minute_candles", lambda client, symbol, limit: _candles([8.0, 10.0, 12.0]))

    rebalance_by_limit_order(FakeClient(), "DOGEUSDT", 1.0)

    assert len(calls["cancel"]) >= 3


def test_timeout_status_is_returned_when_max_duration_is_enabled_and_exceeded(
    monkeypatch: MonkeyPatch,
) -> None:
    calls = _patch_common_rebalancer_dependencies(monkeypatch, positions=[0.0, 0.0])
    times = iter([0.0, 5.0])
    monkeypatch.setattr(rebalancer, "_now_seconds", lambda: next(times))
    monkeypatch.setattr(config, "ENABLE_MAX_REBALANCE_DURATION", 1)
    monkeypatch.setattr(config, "MAX_REBALANCE_DURATION_SECONDS", 1)
    monkeypatch.setattr(rebalancer, "get_minute_candles", lambda client, symbol, limit: _candles([8.0, 10.0, 12.0]))

    result = rebalance_by_limit_order(FakeClient(), "DOGEUSDT", 1.0)

    assert result["status"] == "timeout"
    assert calls["cancel"] == ["DOGEUSDT", "DOGEUSDT"]


def test_rebalance_by_limit_order_skips_leverage_when_prepare_leverage_false(
    monkeypatch: MonkeyPatch,
) -> None:
    calls = _patch_common_rebalancer_dependencies(monkeypatch, positions=[0.0, 1.0])
    monkeypatch.setattr(rebalancer, "get_minute_candles", lambda client, symbol, limit: _candles([10.0, 10.0, 10.0]))

    rebalance_by_limit_order(FakeClient(), "DOGEUSDT", 1.0, prepare_leverage=False)

    assert calls["margin"] == 0
    assert calls["leverage"] == 0


def test_rebalance_by_limit_order_prepares_leverage_when_prepare_leverage_true(
    monkeypatch: MonkeyPatch,
) -> None:
    calls = _patch_common_rebalancer_dependencies(monkeypatch, positions=[0.0, 1.0])
    monkeypatch.setattr(rebalancer, "get_minute_candles", lambda client, symbol, limit: _candles([10.0, 10.0, 10.0]))

    rebalance_by_limit_order(FakeClient(), "DOGEUSDT", 1.0, prepare_leverage=True)

    assert calls["margin"] == 1
    assert calls["leverage"] == 1


def test_rebalance_by_limit_order_rounds_price_before_placing_order(
    monkeypatch: MonkeyPatch,
) -> None:
    calls = _patch_common_rebalancer_dependencies(monkeypatch, positions=[0.0, 0.0, 1.0])
    monkeypatch.setattr(
        rebalancer,
        "get_instrument_info",
        lambda client, symbol: {
            "priceFilter": {"tickSize": "0.05"},
            "lotSizeFilter": {"qtyStep": "0.1"},
        },
    )
    monkeypatch.setattr(rebalancer, "get_minute_candles", lambda client, symbol, limit: _candles([10.01, 10.03, 10.05]))

    rebalance_by_limit_order(FakeClient(), "DOGEUSDT", 1.0)

    assert calls["orders"][0]["price"] == pytest.approx(10.05)


def test_rebalance_by_limit_order_rounds_signed_qty_down_before_placing_order(
    monkeypatch: MonkeyPatch,
) -> None:
    calls = _patch_common_rebalancer_dependencies(monkeypatch, positions=[0.0, 0.0, -1.23])
    monkeypatch.setattr(
        rebalancer,
        "get_instrument_info",
        lambda client, symbol: {
            "priceFilter": {"tickSize": "0.1"},
            "lotSizeFilter": {"qtyStep": "0.5"},
        },
    )
    monkeypatch.setattr(rebalancer, "get_minute_candles", lambda client, symbol, limit: _candles([12.0, 10.0, 8.0]))

    rebalance_by_limit_order(FakeClient(), "DOGEUSDT", -1.23)

    assert calls["orders"][0]["qty"] == pytest.approx(-1.0)


def test_rebalance_by_limit_order_does_not_place_order_if_rounded_qty_is_zero(
    monkeypatch: MonkeyPatch,
) -> None:
    calls = _patch_common_rebalancer_dependencies(monkeypatch, positions=[0.0, 0.0])
    monkeypatch.setattr(config, "MIN_ORDER_NOTIONAL_USDT", 0.001)
    monkeypatch.setattr(
        rebalancer,
        "get_instrument_info",
        lambda client, symbol: {
            "priceFilter": {"tickSize": "0.1"},
            "lotSizeFilter": {"qtyStep": "1"},
        },
    )
    monkeypatch.setattr(rebalancer, "get_minute_candles", lambda client, symbol, limit: _candles([8.0, 10.0, 12.0]))

    result = rebalance_by_limit_order(FakeClient(), "DOGEUSDT", 0.4)

    assert result["status"] == "completed"
    assert calls["orders"] == []


def test_rebalance_by_limit_order_fails_safely_if_instrument_metadata_unavailable(
    monkeypatch: MonkeyPatch,
) -> None:
    calls = _patch_common_rebalancer_dependencies(monkeypatch, positions=[0.0])
    monkeypatch.setattr(rebalancer, "get_instrument_info", lambda client, symbol: None)

    result = rebalance_by_limit_order(FakeClient(), "DOGEUSDT", 1.0)

    assert result["status"] == "failed"
    assert "Instrument metadata is unavailable" in result["error"]
    assert calls["orders"] == []
