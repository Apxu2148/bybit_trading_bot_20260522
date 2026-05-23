from __future__ import annotations

import math
from typing import Any

import pytest
from pytest import MonkeyPatch

from config import config
from strategy import momentum_volatility as strategy


def _patch_strategy_defaults(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(config, "SCORE_LOOKBACK_HOURS", 5)
    monkeypatch.setattr(config, "POSITION_MULTIPLIER", 1.0)
    monkeypatch.setattr(strategy, "TRADE_DIRECTION_MODE", "long_and_short")


def _candles_from_closes(closes: list[Any]) -> list[dict[str, Any]]:
    return [
        {
            "start_time_ms": index * 3_600_000,
            "close": close,
            "turnover": 200_000.0,
        }
        for index, close in enumerate(closes)
    ]


def test_extract_closes_returns_close_values_as_floats() -> None:
    candles = _candles_from_closes(["100", 101, 102.5])

    assert strategy.extract_closes(candles) == [100.0, 101.0, 102.5]


def test_extract_closes_skips_malformed_candles_safely() -> None:
    candles = [
        {"close": "100"},
        {"close": 0},
        {"close": -1},
        {"close": "bad"},
        {"not_close": 10},
        "not-a-candle",
        {"close": 101.5},
    ]

    assert strategy.extract_closes(candles) == [100.0, 101.5]  # type: ignore[arg-type]


def test_calculate_log_returns_works_on_valid_close_series() -> None:
    closes = [100.0, 110.0, 121.0]

    result = strategy.calculate_log_returns(closes)

    assert result == pytest.approx([math.log(1.1), math.log(1.1)])


def test_calculate_trend_computes_log_last_over_first() -> None:
    closes = [100.0, 105.0, 120.0]

    assert strategy.calculate_trend(closes) == pytest.approx(math.log(120.0 / 100.0))


def test_calculate_volatility_returns_positive_value_for_varying_returns() -> None:
    log_returns = [0.01, 0.03, -0.02]

    assert strategy.calculate_volatility(log_returns) > 0


def test_calculate_score_returns_positive_score_for_smooth_uptrend(monkeypatch: MonkeyPatch) -> None:
    _patch_strategy_defaults(monkeypatch)
    candles = _candles_from_closes([100.0, 102.0, 105.0, 109.0, 114.0])

    score = strategy.calculate_score(candles)

    assert score is not None
    assert score > 0


def test_calculate_score_returns_negative_score_for_smooth_downtrend(monkeypatch: MonkeyPatch) -> None:
    _patch_strategy_defaults(monkeypatch)
    candles = _candles_from_closes([114.0, 109.0, 105.0, 102.0, 100.0])

    score = strategy.calculate_score(candles)

    assert score is not None
    assert score < 0


def test_calculate_score_returns_none_if_volatility_is_zero(monkeypatch: MonkeyPatch) -> None:
    _patch_strategy_defaults(monkeypatch)
    candles = _candles_from_closes([100.0, 100.0, 100.0, 100.0, 100.0])

    assert strategy.calculate_score(candles) is None


def test_calculate_target_leverage_returns_positive_for_best_positive_score(
    monkeypatch: MonkeyPatch,
) -> None:
    _patch_strategy_defaults(monkeypatch)
    candles_by_symbol = {
        "UPUSDT": _candles_from_closes([100.0, 102.0, 105.0, 109.0, 114.0]),
        "WEAKUSDT": _candles_from_closes([100.0, 100.5, 101.0, 101.2, 101.6]),
    }

    result = strategy.calculate_target_leverage(
        eligible_symbols=["UPUSDT", "WEAKUSDT"],
        candles_by_symbol=candles_by_symbol,
        position_multiplier=2.5,
    )

    assert result == {"UPUSDT": 2.5}


def test_calculate_target_leverage_returns_negative_for_best_negative_score(
    monkeypatch: MonkeyPatch,
) -> None:
    _patch_strategy_defaults(monkeypatch)
    candles_by_symbol = {
        "WEAKUSDT": _candles_from_closes([100.0, 100.5, 101.0, 101.2, 101.6]),
        "DOWNUSDT": _candles_from_closes([120.0, 114.0, 105.0, 99.0, 90.0]),
    }

    result = strategy.calculate_target_leverage(
        eligible_symbols=["WEAKUSDT", "DOWNUSDT"],
        candles_by_symbol=candles_by_symbol,
        position_multiplier=1.25,
    )

    assert result == {"DOWNUSDT": -1.25}


def test_calculate_target_leverage_returns_empty_if_eligible_symbols_empty(
    monkeypatch: MonkeyPatch,
) -> None:
    _patch_strategy_defaults(monkeypatch)

    result = strategy.calculate_target_leverage(
        eligible_symbols=[],
        candles_by_symbol={},
    )

    assert result == {}


def test_calculate_target_leverage_returns_empty_if_no_symbol_has_valid_score(
    monkeypatch: MonkeyPatch,
) -> None:
    _patch_strategy_defaults(monkeypatch)
    candles_by_symbol = {"FLATUSDT": _candles_from_closes([100.0, 100.0, 100.0, 100.0, 100.0])}

    result = strategy.calculate_target_leverage(
        eligible_symbols=["FLATUSDT"],
        candles_by_symbol=candles_by_symbol,
    )

    assert result == {}


def test_long_only_mode_ignores_negative_scores(monkeypatch: MonkeyPatch) -> None:
    _patch_strategy_defaults(monkeypatch)
    monkeypatch.setattr(strategy, "TRADE_DIRECTION_MODE", "long_only")
    candles_by_symbol = {
        "DOWNUSDT": _candles_from_closes([120.0, 114.0, 105.0, 99.0, 90.0]),
        "UPUSDT": _candles_from_closes([100.0, 100.5, 101.0, 101.2, 101.6]),
    }

    result = strategy.calculate_target_leverage(
        eligible_symbols=["DOWNUSDT", "UPUSDT"],
        candles_by_symbol=candles_by_symbol,
    )

    assert result == {"UPUSDT": 1.0}


def test_short_only_mode_ignores_positive_scores(monkeypatch: MonkeyPatch) -> None:
    _patch_strategy_defaults(monkeypatch)
    monkeypatch.setattr(strategy, "TRADE_DIRECTION_MODE", "short_only")
    candles_by_symbol = {
        "UPUSDT": _candles_from_closes([100.0, 102.0, 105.0, 109.0, 114.0]),
        "DOWNUSDT": _candles_from_closes([100.0, 99.5, 99.0, 98.8, 98.4]),
    }

    result = strategy.calculate_target_leverage(
        eligible_symbols=["UPUSDT", "DOWNUSDT"],
        candles_by_symbol=candles_by_symbol,
    )

    assert result == {"DOWNUSDT": -1.0}


def test_invalid_trade_direction_mode_raises_value_error(monkeypatch: MonkeyPatch) -> None:
    _patch_strategy_defaults(monkeypatch)
    monkeypatch.setattr(strategy, "TRADE_DIRECTION_MODE", "sideways")

    with pytest.raises(ValueError, match="Invalid TRADE_DIRECTION_MODE"):
        strategy.calculate_target_leverage(
            eligible_symbols=["UPUSDT"],
            candles_by_symbol={"UPUSDT": _candles_from_closes([100.0, 102.0, 105.0, 109.0, 114.0])},
        )


def test_rank_symbols_returns_symbols_sorted_by_abs_score_descending(
    monkeypatch: MonkeyPatch,
) -> None:
    _patch_strategy_defaults(monkeypatch)
    scores = {
        "AUSDT": 0.1,
        "BUSDT": -0.5,
        "CUSDT": 0.2,
    }

    def fake_calculate_score(candles: list[dict[str, Any]]) -> float | None:
        return scores[str(candles[0]["symbol"])]

    monkeypatch.setattr(strategy, "calculate_score", fake_calculate_score)
    candles_by_symbol = {
        "AUSDT": [{"symbol": "AUSDT"}],
        "BUSDT": [{"symbol": "BUSDT"}],
        "CUSDT": [{"symbol": "CUSDT"}],
    }

    ranked_symbols = strategy.rank_symbols(
        eligible_symbols=["AUSDT", "BUSDT", "CUSDT"],
        candles_by_symbol=candles_by_symbol,
    )

    assert [item["symbol"] for item in ranked_symbols] == ["BUSDT", "CUSDT", "AUSDT"]
