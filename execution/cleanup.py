"""Cleanup helpers for small leftover positions."""

from __future__ import annotations

import logging
from typing import Any

from bybit.client import BybitClient
from config import config
from execution.orders import place_market_order
from logging_setup.logger import get_loggers


def cleanup_small_positions(
    client: BybitClient,
    current_positions: dict[str, float],
    last_close_prices: dict[str, float],
) -> dict[str, Any]:
    """Try to close positions below the configured small-position threshold."""
    logger = _get_execution_logger()
    summary: dict[str, Any] = {
        "closed": [],
        "failed": [],
        "skipped": [],
    }

    for symbol, qty in current_positions.items():
        price = _to_float(last_close_prices.get(symbol))
        qty_value = _to_float(qty)
        if qty_value is None or qty_value == 0:
            summary["skipped"].append(symbol)
            continue
        if price is None or price <= 0:
            logger.warning("Skipping cleanup for %s due to missing or invalid price.", symbol)
            summary["skipped"].append(symbol)
            continue

        notional = abs(qty_value * price)
        if notional >= config.MIN_POSITION_NOTIONAL_USDT:
            summary["skipped"].append(symbol)
            continue

        close_qty = -qty_value
        logger.info("Attempting small-position cleanup for %s; notional=%s.", symbol, notional)
        if _try_close_position(client, symbol, close_qty, reduce_only=False):
            summary["closed"].append(symbol)
            continue
        if _try_close_position(client, symbol, close_qty, reduce_only=True):
            summary["closed"].append(symbol)
            continue

        logger.error("Small-position cleanup failed for %s after all attempts.", symbol)
        summary["failed"].append(symbol)

    return summary


def _try_close_position(
    client: BybitClient,
    symbol: str,
    close_qty: float,
    reduce_only: bool,
) -> bool:
    """Try market close attempts for one symbol."""
    max_attempts = _cleanup_attempt_count(reduce_only=reduce_only)
    logger = _get_execution_logger()

    for attempt in range(1, max_attempts + 1):
        try:
            place_market_order(
                client=client,
                symbol=symbol,
                qty=close_qty,
                reduce_only=reduce_only,
            )
            logger.info(
                "Small-position cleanup order accepted for %s; reduce_only=%s attempt=%s.",
                symbol,
                reduce_only,
                attempt,
            )
            return True
        except Exception as exc:
            logger.warning(
                "Small-position cleanup attempt failed for %s; reduce_only=%s attempt=%s/%s error_type=%s.",
                symbol,
                reduce_only,
                attempt,
                max_attempts,
                exc.__class__.__name__,
            )

    return False


def _cleanup_attempt_count(reduce_only: bool) -> int:
    """Return configured cleanup attempts for normal or reduce-only closes."""
    if reduce_only:
        return max(int(config.SMALL_POSITION_CLEANUP_MAX_REDUCE_ONLY_ATTEMPTS), 0)
    return max(int(config.SMALL_POSITION_CLEANUP_MAX_MARKET_ATTEMPTS), 0)


def _to_float(value: Any) -> float | None:
    """Convert a value to float without raising."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _get_execution_logger() -> logging.Logger:
    """Return the configured execution logger."""
    return get_loggers()["execution"]
