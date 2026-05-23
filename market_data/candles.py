"""Candle loading and latest-candle completeness utilities."""

from __future__ import annotations

import logging
import time
from typing import Any

from bybit.client import BybitClient
from logging_setup.logger import get_loggers


NORMALIZED_CANDLE_KEYS = (
    "start_time_ms",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "turnover",
)


def get_candles(
    client: BybitClient,
    symbol: str,
    interval: str,
    limit: int,
) -> list[dict[str, Any]]:
    """Load, normalize, sort, and latest-candle-filter Bybit kline data."""
    logger = _get_filtering_logger()
    response = client.get_kline(category="linear", symbol=symbol, interval=interval, limit=limit)
    raw_candles = _extract_result_list(response, symbol)
    normalized_candles: list[dict[str, Any]] = []

    for raw_candle in raw_candles:
        normalized_candle = _normalize_candle(raw_candle, symbol)
        if normalized_candle is not None:
            normalized_candles.append(normalized_candle)

    normalized_candles.sort(key=lambda candle: candle["start_time_ms"])
    interval_seconds = _interval_to_seconds(interval)
    if interval_seconds is None:
        logger.warning(
            "Skipping unfinished-candle filter for %s because interval %s is unsupported.",
            symbol,
            interval,
        )
        return normalized_candles

    return filter_unfinished_last_candle(normalized_candles, interval_seconds)


def get_hourly_candles(
    client: BybitClient,
    symbol: str,
    limit: int,
) -> list[dict[str, Any]]:
    """Load hourly candles for a symbol."""
    return get_candles(client=client, symbol=symbol, interval="60", limit=limit)


def get_minute_candles(
    client: BybitClient,
    symbol: str,
    limit: int,
) -> list[dict[str, Any]]:
    """Load one-minute candles for a symbol."""
    return get_candles(client=client, symbol=symbol, interval="1", limit=limit)


def get_last_close(
    candles: list[dict[str, Any]],
) -> float | None:
    """Return the close from the last valid candle in a filtered candle list."""
    for candle in reversed(candles):
        close = _to_float(candle.get("close") if isinstance(candle, dict) else None)
        if close is not None:
            return close
    return None


def should_include_last_candle(
    candle_start_ms: int,
    interval_seconds: int,
    now_ms: int | None = None,
) -> bool:
    """Return True only when more than 50 percent of a candle has elapsed."""
    if interval_seconds <= 0:
        return False

    current_ms = int(time.time() * 1000) if now_ms is None else now_ms
    elapsed_ms = current_ms - candle_start_ms
    if elapsed_ms <= 0:
        return False

    interval_ms = interval_seconds * 1000
    return elapsed_ms > interval_ms / 2


def filter_unfinished_last_candle(
    candles: list[dict[str, Any]],
    interval_seconds: int,
) -> list[dict[str, Any]]:
    """Remove the latest candle unless more than half its period has elapsed."""
    valid_candles = _sort_valid_candles(candles)
    if not valid_candles:
        return []

    latest_candle = valid_candles[-1]
    if should_include_last_candle(
        candle_start_ms=int(latest_candle["start_time_ms"]),
        interval_seconds=interval_seconds,
    ):
        return valid_candles

    return valid_candles[:-1]


def _extract_result_list(response: Any, symbol: str) -> list[Any]:
    """Extract Bybit V5 ``result.list`` kline rows safely."""
    logger = _get_filtering_logger()
    # Bybit V5 kline responses are expected to be dictionaries with candle
    # rows under result.list. Each row is usually newest-first from Bybit, so
    # callers normalize and sort before using the data.
    if not isinstance(response, dict):
        logger.warning("Skipping candles for %s; response_type=%s.", symbol, type(response).__name__)
        return []

    result = response.get("result")
    if not isinstance(result, dict):
        logger.warning("Skipping candles for %s; missing result object.", symbol)
        return []

    raw_candles = result.get("list")
    if not isinstance(raw_candles, list):
        logger.warning("Skipping candles for %s; missing result list.", symbol)
        return []

    return raw_candles


def _normalize_candle(raw_candle: Any, symbol: str) -> dict[str, Any] | None:
    """Normalize one Bybit kline row into project candle fields.

    Bybit V5 kline rows are arrays ordered as:
    start time, open, high, low, close, volume, and turnover.
    Numeric values usually arrive as strings.
    """
    logger = _get_filtering_logger()
    if not isinstance(raw_candle, (list, tuple)) or len(raw_candle) < len(NORMALIZED_CANDLE_KEYS):
        logger.warning("Skipping malformed candle for %s; row_type=%s.", symbol, type(raw_candle).__name__)
        return None

    start_time_ms = _to_int(raw_candle[0])
    values = [_to_float(value) for value in raw_candle[1:7]]
    if start_time_ms is None or any(value is None for value in values):
        logger.warning("Skipping malformed candle for %s; numeric parsing failed.", symbol)
        return None

    open_price, high_price, low_price, close_price, volume, turnover = values
    return {
        "start_time_ms": start_time_ms,
        "open": float(open_price),
        "high": float(high_price),
        "low": float(low_price),
        "close": float(close_price),
        "volume": float(volume),
        "turnover": float(turnover),
    }


def _sort_valid_candles(candles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return candles with valid start times sorted ascending."""
    logger = _get_filtering_logger()
    valid_candles: list[dict[str, Any]] = []

    for candle in candles:
        if not isinstance(candle, dict):
            logger.warning("Skipping malformed normalized candle; row_type=%s.", type(candle).__name__)
            continue

        start_time_ms = _to_int(candle.get("start_time_ms"))
        if start_time_ms is None:
            logger.warning("Skipping malformed normalized candle with missing start_time_ms.")
            continue

        copied_candle = dict(candle)
        copied_candle["start_time_ms"] = start_time_ms
        valid_candles.append(copied_candle)

    valid_candles.sort(key=lambda candle: candle["start_time_ms"])
    return valid_candles


def _interval_to_seconds(interval: str) -> int | None:
    """Convert a Bybit kline interval string to seconds."""
    if interval.isdigit():
        return int(interval) * 60

    fixed_intervals = {
        "D": 24 * 60 * 60,
        "W": 7 * 24 * 60 * 60,
        "M": 30 * 24 * 60 * 60,
    }
    return fixed_intervals.get(interval.upper())


def _to_int(value: Any) -> int | None:
    """Convert a value to int without raising."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_float(value: Any) -> float | None:
    """Convert a value to float without raising."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _get_filtering_logger() -> logging.Logger:
    """Return the configured filtering logger."""
    return get_loggers()["filtering"]
