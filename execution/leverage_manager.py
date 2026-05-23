"""Low-level leverage and margin setup helpers."""

from __future__ import annotations

import logging
from typing import Any

from bybit.client import BybitClient
from config import config
from logging_setup.logger import get_loggers


def try_set_leverage_from_candidates(
    client: BybitClient,
    symbol: str,
    leverage_candidates: list[int] | None = None,
) -> float | None:
    """Try leverage candidates without lowering existing leverage."""
    logger = _get_execution_logger()
    candidates = list(config.LEVERAGE_CANDIDATES if leverage_candidates is None else leverage_candidates)
    current_leverage = get_current_leverage(client, symbol)

    if current_leverage is not None:
        logger.info("Current leverage for %s: %s.", symbol, current_leverage)
    else:
        logger.info("Current leverage for %s is unavailable; trying candidates normally.", symbol)

    for candidate in candidates:
        if current_leverage is not None and float(candidate) <= current_leverage:
            logger.info(
                "Stopping leverage attempts for %s at candidate=%s because current leverage is %s.",
                symbol,
                candidate,
                current_leverage,
            )
            logger.info("Final selected leverage for %s: %s.", symbol, current_leverage)
            return current_leverage

        try:
            logger.info("Trying leverage candidate for %s: %s.", symbol, candidate)
            client.set_leverage(
                symbol=symbol,
                buy_leverage=str(candidate),
                sell_leverage=str(candidate),
                category="linear",
            )
            logger.info("Leverage accepted for %s: %s.", symbol, candidate)
            logger.info("Final selected leverage for %s: %s.", symbol, candidate)
            return float(candidate)
        except Exception as exc:
            logger.warning(
                "Leverage candidate failed for %s: leverage=%s error_type=%s.",
                symbol,
                candidate,
                exc.__class__.__name__,
            )

    if current_leverage is not None:
        logger.warning(
            "All leverage candidates above current leverage failed for %s; keeping current leverage %s.",
            symbol,
            current_leverage,
        )
        logger.info("Final selected leverage for %s: %s.", symbol, current_leverage)
        return current_leverage

    logger.warning("No leverage candidate was accepted for %s.", symbol)
    return None


def get_current_leverage(
    client: BybitClient,
    symbol: str,
) -> float | None:
    """Read current leverage for a symbol from Bybit position data."""
    logger = _get_execution_logger()
    try:
        response = client.get_positions(category="linear", symbol=symbol, settle_coin="USDT")
    except Exception as exc:
        logger.warning("Could not read current leverage for %s; error_type=%s.", symbol, exc.__class__.__name__)
        return None

    position = _find_position_row(response, symbol)
    if position is None:
        logger.warning("Could not find position data for %s while reading leverage.", symbol)
        return None

    buy_leverage = _to_float(position.get("buyLeverage"))
    sell_leverage = _to_float(position.get("sellLeverage"))
    if buy_leverage is not None and sell_leverage is not None:
        if buy_leverage != sell_leverage:
            logger.warning(
                "Buy and sell leverage differ for %s; buy=%s sell=%s. Using lower value.",
                symbol,
                buy_leverage,
                sell_leverage,
            )
        return min(buy_leverage, sell_leverage)

    leverage = _to_float(position.get("leverage"))
    if leverage is not None:
        return leverage

    logger.warning("Position data for %s does not contain parseable leverage.", symbol)
    return None


def try_set_cross_margin_if_possible(
    client: BybitClient,
    symbol: str,
    category: str = "linear",
) -> bool:
    """Try to set cross margin when the exchange/client supports it."""
    logger = _get_execution_logger()
    try:
        client.set_margin_mode(category=category, symbol=symbol, tradeMode=0)
        logger.info("Cross margin setup accepted for %s.", symbol)
        return True
    except Exception as exc:
        logger.warning(
            "Cross margin setup was not accepted for %s; error_type=%s.",
            symbol,
            exc.__class__.__name__,
        )
        return False


def _get_execution_logger() -> logging.Logger:
    """Return the configured execution logger."""
    return get_loggers()["execution"]


def _find_position_row(response: Any, symbol: str) -> dict[str, Any] | None:
    """Find a Bybit V5 position row for the requested symbol."""
    if not isinstance(response, dict):
        return None
    result = response.get("result")
    if not isinstance(result, dict):
        return None
    rows = result.get("list")
    if not isinstance(rows, list):
        return None

    for row in rows:
        if isinstance(row, dict) and row.get("symbol") == symbol:
            return row
    return None


def _to_float(value: Any) -> float | None:
    """Convert a value to float without raising."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
