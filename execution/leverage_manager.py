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
) -> int | None:
    """Try leverage candidates in order and return the first accepted value."""
    logger = _get_execution_logger()
    candidates = list(config.LEVERAGE_CANDIDATES if leverage_candidates is None else leverage_candidates)

    for candidate in candidates:
        try:
            logger.info("Trying leverage candidate for %s: %s.", symbol, candidate)
            client.set_leverage(
                symbol=symbol,
                buy_leverage=str(candidate),
                sell_leverage=str(candidate),
                category="linear",
            )
            logger.info("Leverage accepted for %s: %s.", symbol, candidate)
            return candidate
        except Exception as exc:
            logger.warning(
                "Leverage candidate failed for %s: leverage=%s error_type=%s.",
                symbol,
                candidate,
                exc.__class__.__name__,
            )

    logger.warning("No leverage candidate was accepted for %s.", symbol)
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
