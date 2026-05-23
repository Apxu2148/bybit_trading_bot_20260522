from __future__ import annotations

from typing import Any

from pytest import MonkeyPatch

from config import config
from market_data.filters import apply_filters


def _patch_base_filter_config(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(config, "SCORE_LOOKBACK_HOURS", 3)
    monkeypatch.setattr(config, "MIN_AVG_HOURLY_VOLUME", 100_000)
    monkeypatch.setattr(config, "ENABLE_STABLECOIN_PRICE_FILTER", 1)
    monkeypatch.setattr(config, "STABLECOIN_PRICE_LOWER_BOUND", 0.9)
    monkeypatch.setattr(config, "STABLECOIN_PRICE_UPPER_BOUND", 1.1)
    monkeypatch.setattr(config, "SYMBOL_BLACKLIST", [])
    monkeypatch.setattr(config, "ENABLE_SPREAD_FILTER", 0)
    monkeypatch.setattr(config, "ENABLE_FUNDING_FILTER", 0)
    monkeypatch.setattr(config, "ENABLE_EMA_DISTANCE_FILTER", 0)
    monkeypatch.setattr(config, "MAX_ABS_FUNDING_RATE", 0.005)
    monkeypatch.setattr(config, "EMA_DISTANCE_PERIOD", 3)
    monkeypatch.setattr(config, "MAX_EMA_DISTANCE", 0.12)


def _candles(count: int, turnover: float, close: float = 10.0) -> list[dict[str, Any]]:
    return [
        {
            "start_time_ms": index * 3_600_000,
            "close": close,
            "turnover": turnover,
        }
        for index in range(count)
    ]


def test_passes_symbol_with_enough_history_volume_and_valid_price(monkeypatch: MonkeyPatch) -> None:
    _patch_base_filter_config(monkeypatch)

    result = apply_filters(
        symbols=["BTCUSDT"],
        candles_by_symbol={"BTCUSDT": _candles(3, 150_000, close=10.0)},
        last_close_by_symbol={"BTCUSDT": 10.0},
    )

    assert result == ["BTCUSDT"]


def test_excludes_symbol_with_insufficient_history(monkeypatch: MonkeyPatch) -> None:
    _patch_base_filter_config(monkeypatch)

    result = apply_filters(
        symbols=["BTCUSDT"],
        candles_by_symbol={"BTCUSDT": _candles(2, 150_000, close=10.0)},
        last_close_by_symbol={"BTCUSDT": 10.0},
    )

    assert result == []


def test_excludes_symbol_with_low_average_turnover(monkeypatch: MonkeyPatch) -> None:
    _patch_base_filter_config(monkeypatch)

    result = apply_filters(
        symbols=["BTCUSDT"],
        candles_by_symbol={"BTCUSDT": _candles(3, 99_999, close=10.0)},
        last_close_by_symbol={"BTCUSDT": 10.0},
    )

    assert result == []


def test_excludes_symbol_with_last_close_inside_stablecoin_range(monkeypatch: MonkeyPatch) -> None:
    _patch_base_filter_config(monkeypatch)

    result = apply_filters(
        symbols=["USDCUSDT"],
        candles_by_symbol={"USDCUSDT": _candles(3, 150_000, close=1.0)},
        last_close_by_symbol={"USDCUSDT": 1.0},
    )

    assert result == []


def test_excludes_blacklisted_symbol(monkeypatch: MonkeyPatch) -> None:
    _patch_base_filter_config(monkeypatch)
    monkeypatch.setattr(config, "SYMBOL_BLACKLIST", ["BTCUSDT"])

    result = apply_filters(
        symbols=["BTCUSDT"],
        candles_by_symbol={"BTCUSDT": _candles(3, 150_000, close=10.0)},
        last_close_by_symbol={"BTCUSDT": 10.0},
    )

    assert result == []


def test_optional_funding_filter_uses_absolute_funding_rate(monkeypatch: MonkeyPatch) -> None:
    _patch_base_filter_config(monkeypatch)
    monkeypatch.setattr(config, "ENABLE_FUNDING_FILTER", 1)
    monkeypatch.setattr(config, "MAX_ABS_FUNDING_RATE", 0.005)

    result = apply_filters(
        symbols=["BTCUSDT"],
        candles_by_symbol={"BTCUSDT": _candles(3, 150_000, close=10.0)},
        last_close_by_symbol={"BTCUSDT": 10.0},
        tickers_by_symbol={"BTCUSDT": {"fundingRate": "-0.006"}},
    )

    assert result == []


def test_optional_ema_distance_filter_excludes_overextended_symbol(monkeypatch: MonkeyPatch) -> None:
    _patch_base_filter_config(monkeypatch)
    monkeypatch.setattr(config, "ENABLE_EMA_DISTANCE_FILTER", 1)
    monkeypatch.setattr(config, "EMA_DISTANCE_PERIOD", 3)
    monkeypatch.setattr(config, "MAX_EMA_DISTANCE", 0.1)
    candles = [
        {"start_time_ms": 1, "close": 100.0, "turnover": 150_000.0},
        {"start_time_ms": 2, "close": 100.0, "turnover": 150_000.0},
        {"start_time_ms": 3, "close": 200.0, "turnover": 150_000.0},
    ]

    result = apply_filters(
        symbols=["BTCUSDT"],
        candles_by_symbol={"BTCUSDT": candles},
        last_close_by_symbol={"BTCUSDT": 200.0},
    )

    assert result == []


def test_returns_empty_list_if_no_symbols_pass_filters(monkeypatch: MonkeyPatch) -> None:
    _patch_base_filter_config(monkeypatch)

    result = apply_filters(
        symbols=["LOWUSDT", "USDCUSDT"],
        candles_by_symbol={
            "LOWUSDT": _candles(3, 10_000, close=10.0),
            "USDCUSDT": _candles(3, 150_000, close=1.0),
        },
        last_close_by_symbol={"LOWUSDT": 10.0, "USDCUSDT": 1.0},
    )

    assert result == []
