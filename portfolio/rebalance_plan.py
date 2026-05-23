"""Pure rebalance plan calculations."""

from __future__ import annotations

import logging
from typing import Any

from config import config
from logging_setup.logger import get_loggers


def calculate_target_positions(
    target_leverage: dict[str, float],
    total_equity: float,
    last_close_prices: dict[str, float],
) -> dict[str, float]:
    """Convert target leverage into target position quantities."""
    logger = _get_main_logger()
    target_positions: dict[str, float] = {}

    for symbol, leverage in target_leverage.items():
        last_close_price = _to_float(last_close_prices.get(symbol))
        if last_close_price is None or last_close_price <= 0:
            logger.warning("Skipping target position for %s due to missing or invalid last close price.", symbol)
            continue

        leverage_value = _to_float(leverage)
        if leverage_value is None:
            logger.warning("Skipping target position for %s due to malformed target leverage.", symbol)
            continue

        target_notional = leverage_value * float(total_equity)
        target_positions[symbol] = target_notional / last_close_price

    logger.info("Target positions calculated: %s.", target_positions)
    return target_positions


def align_position_keys(
    current_positions: dict[str, float],
    target_positions: dict[str, float],
) -> tuple[dict[str, float], dict[str, float]]:
    """Align current and target position dictionaries on their symbol union."""
    symbols = sorted(set(current_positions) | set(target_positions))
    current_aligned = {
        symbol: _float_or_zero(current_positions.get(symbol))
        for symbol in symbols
    }
    target_aligned = {
        symbol: _float_or_zero(target_positions.get(symbol))
        for symbol in symbols
    }
    return current_aligned, target_aligned


def calculate_delta_qty(
    current_positions: dict[str, float],
    target_positions: dict[str, float],
    last_close_prices: dict[str, float],
) -> dict[str, float]:
    """Calculate rebalance delta quantities without executing orders."""
    logger = _get_main_logger()
    current_aligned, target_aligned = align_position_keys(current_positions, target_positions)
    delta_qty: dict[str, float] = {}

    for symbol in current_aligned:
        delta = target_aligned[symbol] - current_aligned[symbol]
        if delta == 0:
            delta_qty[symbol] = 0.0
            continue

        last_close_price = _to_float(last_close_prices.get(symbol))
        if last_close_price is None or last_close_price <= 0:
            logger.warning("Setting delta quantity for %s to zero due to missing or invalid price.", symbol)
            delta_qty[symbol] = 0.0
            continue

        notional = abs(delta * last_close_price)
        if notional < config.MIN_ORDER_NOTIONAL_USDT:
            logger.info(
                "Setting delta quantity for %s to zero because notional %s is below minimum %s.",
                symbol,
                notional,
                config.MIN_ORDER_NOTIONAL_USDT,
            )
            delta_qty[symbol] = 0.0
            continue

        delta_qty[symbol] = delta

    logger.info("Delta quantities calculated: %s.", delta_qty)
    return delta_qty


def build_rebalance_plan(
    current_positions: dict[str, float],
    target_leverage: dict[str, float],
    total_equity: float,
    last_close_prices: dict[str, float],
) -> dict[str, Any]:
    """Build a complete rebalance plan without executing it."""
    target_positions = calculate_target_positions(
        target_leverage=target_leverage,
        total_equity=total_equity,
        last_close_prices=last_close_prices,
    )
    current_aligned, target_aligned = align_position_keys(current_positions, target_positions)
    delta_qty = calculate_delta_qty(
        current_positions=current_aligned,
        target_positions=target_aligned,
        last_close_prices=last_close_prices,
    )

    return {
        "target_positions": target_positions,
        "current_positions_aligned": current_aligned,
        "target_positions_aligned": target_aligned,
        "delta_qty": delta_qty,
    }


def _to_float(value: Any) -> float | None:
    """Convert a value to float without raising."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _float_or_zero(value: Any) -> float:
    """Convert a value to float or return zero for missing/malformed values."""
    converted = _to_float(value)
    return 0.0 if converted is None else converted


def _get_main_logger() -> logging.Logger:
    """Return the configured main logger."""
    return get_loggers()["main"]
