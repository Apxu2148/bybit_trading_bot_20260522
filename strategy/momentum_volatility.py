"""Momentum-volatility target leverage strategy."""

from __future__ import annotations

import logging
import math
from typing import Any

from config import config
from logging_setup.logger import get_loggers

TRADE_DIRECTION_MODE = "long_and_short"

ALLOWED_TRADE_DIRECTION_MODES = {
    "long_and_short",
    "long_only",
    "short_only",
}


def calculate_target_leverage(
    eligible_symbols: list[str],
    candles_by_symbol: dict[str, list[dict[str, Any]]],
    position_multiplier: float | None = None,
) -> dict[str, float]:
    """Calculate the strategy target leverage for the strongest symbol."""
    logger = _get_main_logger()
    logger.info("Momentum-volatility strategy received %s eligible symbol(s).", len(eligible_symbols))

    ranked_symbols = rank_symbols(
        eligible_symbols=eligible_symbols,
        candles_by_symbol=candles_by_symbol,
    )
    logger.info("Momentum-volatility strategy produced %s valid score(s).", len(ranked_symbols))
    logger.info("Top 10 symbols by abs(score): %s.", ranked_symbols[:10])

    best_symbol = select_best_symbol(ranked_symbols)
    if best_symbol is None:
        target_leverage: dict[str, float] = {}
        logger.info("Momentum-volatility strategy selected no symbol.")
        logger.info("Final target leverage: %s.", target_leverage)
        return target_leverage

    score = float(best_symbol["score"])
    symbol = str(best_symbol["symbol"])
    multiplier = float(config.POSITION_MULTIPLIER if position_multiplier is None else position_multiplier)

    if score > 0:
        target_leverage = {symbol: multiplier}
        direction = "long"
    elif score < 0:
        target_leverage = {symbol: -multiplier}
        direction = "short"
    else:
        target_leverage = {}
        direction = "flat"

    logger.info("Momentum-volatility strategy selected symbol: %s.", symbol)
    logger.info("Momentum-volatility strategy selected direction: %s.", direction)
    logger.info("Final target leverage: %s.", target_leverage)
    return target_leverage


def extract_closes(candles: list[dict[str, Any]]) -> list[float]:
    """Extract positive close prices as floats, skipping malformed candles."""
    closes: list[float] = []
    for candle in candles:
        if not isinstance(candle, dict):
            continue

        close = _to_float(candle.get("close"))
        if close is None or close <= 0:
            continue

        closes.append(close)

    return closes


def calculate_log_returns(closes: list[float]) -> list[float]:
    """Calculate hourly log returns from a valid close-price series."""
    log_returns: list[float] = []
    if len(closes) < 2:
        return log_returns

    for previous_close, current_close in zip(closes, closes[1:]):
        if previous_close <= 0 or current_close <= 0:
            return []
        log_returns.append(math.log(current_close / previous_close))

    return log_returns


def calculate_trend(closes: list[float]) -> float:
    """Calculate total log trend over a close-price series."""
    if len(closes) < 2 or closes[0] <= 0 or closes[-1] <= 0:
        return 0.0
    return math.log(closes[-1] / closes[0])


def calculate_volatility(log_returns: list[float]) -> float:
    """Calculate population standard deviation of hourly log returns."""
    if not log_returns:
        return 0.0

    mean_return = sum(log_returns) / len(log_returns)
    variance = sum((log_return - mean_return) ** 2 for log_return in log_returns) / len(log_returns)
    return math.sqrt(variance)


def calculate_score(candles: list[dict[str, Any]]) -> float | None:
    """Calculate the momentum-volatility score for one symbol.

    Formula:
        score = trend * abs(trend) / volatility

    A positive trend produces a positive score, while a negative trend produces
    a negative score. Squaring the trend magnitude rewards stronger moves, and
    dividing by volatility penalizes noisy hourly return paths.
    """
    lookback_hours = int(config.SCORE_LOOKBACK_HOURS)
    if lookback_hours < 2 or len(candles) < lookback_hours:
        return None

    lookback_candles = candles[-lookback_hours:]
    closes = extract_closes(lookback_candles)
    if len(closes) != lookback_hours:
        return None

    log_returns = calculate_log_returns(closes)
    if len(log_returns) != lookback_hours - 1:
        return None

    trend = calculate_trend(closes)
    volatility = calculate_volatility(log_returns)
    if volatility == 0:
        return None

    return trend * abs(trend) / volatility


def rank_symbols(
    eligible_symbols: list[str],
    candles_by_symbol: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Return scored symbols sorted by absolute score descending."""
    _validate_trade_direction_mode(TRADE_DIRECTION_MODE)
    ranked_symbols: list[dict[str, Any]] = []

    for symbol in eligible_symbols:
        candles = candles_by_symbol.get(symbol, [])
        score = calculate_score(candles)
        if score is None or not _score_allowed_by_direction(score):
            continue

        ranked_symbols.append(
            {
                "symbol": symbol,
                "score": score,
                "abs_score": abs(score),
            }
        )

    ranked_symbols.sort(key=lambda item: float(item["abs_score"]), reverse=True)
    return ranked_symbols


def select_best_symbol(
    ranked_symbols: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Return the highest-ranked symbol or None when no symbols are valid."""
    if not ranked_symbols:
        return None
    return ranked_symbols[0]


def _score_allowed_by_direction(score: float) -> bool:
    """Return True when a score is tradable under the active direction mode."""
    if TRADE_DIRECTION_MODE == "long_and_short":
        return score != 0
    if TRADE_DIRECTION_MODE == "long_only":
        return score > 0
    if TRADE_DIRECTION_MODE == "short_only":
        return score < 0
    _validate_trade_direction_mode(TRADE_DIRECTION_MODE)
    return False


def _validate_trade_direction_mode(mode: str) -> None:
    """Raise ValueError when the configured strategy direction mode is invalid."""
    if mode not in ALLOWED_TRADE_DIRECTION_MODES:
        allowed = ", ".join(sorted(ALLOWED_TRADE_DIRECTION_MODES))
        raise ValueError(f"Invalid TRADE_DIRECTION_MODE '{mode}'. Allowed values: {allowed}.")


def _to_float(value: Any) -> float | None:
    """Convert a value to float without raising."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _get_main_logger() -> logging.Logger:
    """Return the configured main logger."""
    return get_loggers()["main"]
