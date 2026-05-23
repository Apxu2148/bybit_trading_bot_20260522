"""Moving-average based limit-order rebalancer."""

from __future__ import annotations

import logging
import time
from typing import Any

from bybit.client import BybitClient
from config import config
from execution.leverage_manager import (
    try_set_cross_margin_if_possible,
    try_set_leverage_from_candidates,
)
from execution.orders import cancel_all_orders_for_symbol, place_limit_order
from logging_setup.logger import get_loggers
from market_data.candles import get_minute_candles
from market_data.instruments import get_instrument_info
from portfolio.positions import get_current_positions
from utils.rounding import round_price_to_tick, round_qty_abs_down

ACTIVE_REBALANCE_SYMBOLS: set[str] = set()


class RebalanceError(Exception):
    """Base exception for limit rebalancer errors."""


class RebalanceAlreadyActiveError(RebalanceError):
    """Raised when a rebalance is already active for the same symbol."""


def calculate_simple_ma(
    candles: list[dict[str, Any]],
    period: int,
) -> float | None:
    """Calculate a simple moving average from the latest candle closes."""
    if period <= 0 or len(candles) < period:
        return None

    closes: list[float] = []
    for candle in candles[-period:]:
        close = _to_float(candle.get("close") if isinstance(candle, dict) else None)
        if close is None:
            return None
        closes.append(close)

    return sum(closes) / period


def get_latest_close(
    candles: list[dict[str, Any]],
) -> float | None:
    """Return the close from the latest usable candle."""
    for candle in reversed(candles):
        close = _to_float(candle.get("close") if isinstance(candle, dict) else None)
        if close is not None:
            return close
    return None


def should_place_limit_order(
    qty_delta: float,
    latest_close: float,
    ma_value: float,
) -> bool:
    """Return whether the MA condition allows a limit order now."""
    if qty_delta > 0:
        return latest_close > ma_value
    if qty_delta < 0:
        return latest_close < ma_value
    return False


def calculate_target_position_qty(
    current_position_qty: float,
    qty_delta: float,
) -> float:
    """Return the target position quantity after applying the requested delta."""
    return current_position_qty + qty_delta


def calculate_remaining_delta(
    current_position_qty: float,
    target_position_qty: float,
) -> float:
    """Return remaining signed quantity needed to reach target position."""
    return target_position_qty - current_position_qty


def is_rebalance_complete(
    remaining_delta: float,
    last_close_price: float,
) -> bool:
    """Return True when remaining notional is below ordinary order minimum."""
    return abs(remaining_delta * last_close_price) < config.MIN_ORDER_NOTIONAL_USDT


def rebalance_by_limit_order(
    client: BybitClient,
    symbol: str,
    qty_delta: float,
    prepare_leverage: bool = True,
) -> dict[str, Any]:
    """Rebalance one symbol by repeatedly placing MA-priced limit orders."""
    if qty_delta == 0:
        return {
            "status": "completed",
            "symbol": symbol,
            "requested_qty_delta": qty_delta,
            "target_position_qty": None,
            "remaining_delta": 0.0,
            "orders_placed": 0,
            "iterations": 0,
        }

    active_key = symbol.upper()
    if active_key in ACTIVE_REBALANCE_SYMBOLS:
        raise RebalanceAlreadyActiveError(f"Rebalance is already active for {symbol}.")

    ACTIVE_REBALANCE_SYMBOLS.add(active_key)
    logger = _get_execution_logger()
    start_time = _now_seconds()
    orders_placed = 0
    iterations = 0
    target_position_qty: float | None = None
    remaining_delta = qty_delta

    try:
        logger.info("Starting limit rebalance for %s; requested_qty_delta=%s.", symbol, qty_delta)
        initial_position_qty = _get_symbol_position_qty(client, symbol)
        target_position_qty = calculate_target_position_qty(initial_position_qty, qty_delta)
        logger.info(
            "Limit rebalance target for %s; current_position=%s target_position=%s.",
            symbol,
            initial_position_qty,
            target_position_qty,
        )

        _cancel_orders(client, symbol)
        if prepare_leverage:
            try_set_cross_margin_if_possible(client, symbol)
            try_set_leverage_from_candidates(client, symbol)
        else:
            logger.info("Skipping leverage preparation for %s.", symbol)

        try:
            tick_size, qty_step = _load_tick_size_and_qty_step(client, symbol)
        except Exception as exc:
            error_message = f"Instrument metadata unavailable for {symbol}: {exc}"
            logger.error("Limit rebalance cannot continue for %s; error_type=%s.", symbol, exc.__class__.__name__)
            _cancel_orders(client, symbol)
            return _summary(
                status="failed",
                symbol=symbol,
                requested_qty_delta=qty_delta,
                target_position_qty=target_position_qty,
                remaining_delta=remaining_delta,
                orders_placed=orders_placed,
                iterations=iterations,
                error=error_message,
            )

        logger.info("Instrument rounding metadata for %s; tick_size=%s qty_step=%s.", symbol, tick_size, qty_step)

        while True:
            iterations += 1
            if _is_timeout_enabled() and _now_seconds() - start_time >= float(config.MAX_REBALANCE_DURATION_SECONDS):
                logger.warning("Limit rebalance timed out for %s.", symbol)
                _cancel_orders(client, symbol)
                return _summary(
                    status="timeout",
                    symbol=symbol,
                    requested_qty_delta=qty_delta,
                    target_position_qty=target_position_qty,
                    remaining_delta=remaining_delta,
                    orders_placed=orders_placed,
                    iterations=iterations,
                )

            current_position_qty = _get_symbol_position_qty(client, symbol)
            remaining_delta = calculate_remaining_delta(current_position_qty, target_position_qty)
            candles = _load_rebalance_candles(client, symbol)
            latest_close = get_latest_close(candles)
            ma_value = calculate_simple_ma(candles, int(config.LIMIT_MA_PERIOD_MINUTES))

            logger.info(
                "Limit rebalance check for %s; current_position=%s target_position=%s "
                "remaining_delta=%s latest_close=%s ma_value=%s.",
                symbol,
                current_position_qty,
                target_position_qty,
                remaining_delta,
                latest_close,
                ma_value,
            )

            if latest_close is not None and is_rebalance_complete(remaining_delta, latest_close):
                logger.info("Limit rebalance completed for %s.", symbol)
                _cancel_orders(client, symbol)
                return _summary(
                    status="completed",
                    symbol=symbol,
                    requested_qty_delta=qty_delta,
                    target_position_qty=target_position_qty,
                    remaining_delta=remaining_delta,
                    orders_placed=orders_placed,
                    iterations=iterations,
                )

            if latest_close is None or ma_value is None:
                logger.warning("Limit rebalance data unavailable for %s; waiting for next check.", symbol)
                _sleep_check_interval()
                continue

            condition_met = should_place_limit_order(remaining_delta, latest_close, ma_value)
            logger.info("Limit rebalance order condition for %s: %s.", symbol, condition_met)
            if not condition_met:
                _sleep_check_interval()
                continue

            rounded_price = round_price_to_tick(ma_value, tick_size)
            rounded_qty = round_qty_abs_down(remaining_delta, qty_step)
            logger.info(
                "Rounded MA limit order values for %s; raw_qty=%s rounded_qty=%s raw_price=%s rounded_price=%s.",
                symbol,
                remaining_delta,
                rounded_qty,
                ma_value,
                rounded_price,
            )
            if rounded_qty == 0.0:
                logger.warning("Rounded quantity for %s is zero; no ordinary limit order is needed.", symbol)
                _cancel_orders(client, symbol)
                return _summary(
                    status="completed",
                    symbol=symbol,
                    requested_qty_delta=qty_delta,
                    target_position_qty=target_position_qty,
                    remaining_delta=remaining_delta,
                    orders_placed=orders_placed,
                    iterations=iterations,
                )

            if is_rebalance_complete(rounded_qty, rounded_price):
                logger.info("Rounded remaining notional for %s is below minimum; rebalance is complete.", symbol)
                _cancel_orders(client, symbol)
                return _summary(
                    status="completed",
                    symbol=symbol,
                    requested_qty_delta=qty_delta,
                    target_position_qty=target_position_qty,
                    remaining_delta=remaining_delta,
                    orders_placed=orders_placed,
                    iterations=iterations,
                )

            logger.info("Placing MA limit order for %s; qty=%s price=%s.", symbol, rounded_qty, rounded_price)
            place_limit_order(
                client=client,
                symbol=symbol,
                qty=rounded_qty,
                price=rounded_price,
            )
            orders_placed += 1
            _sleep_check_interval()
            _cancel_orders(client, symbol)
    except Exception as exc:
        logger.error("Limit rebalance failed for %s; error_type=%s.", symbol, exc.__class__.__name__)
        raise
    finally:
        ACTIVE_REBALANCE_SYMBOLS.discard(active_key)


def _load_rebalance_candles(client: BybitClient, symbol: str) -> list[dict[str, Any]]:
    """Load recent one-minute candles with the centralized unfinished-candle rule."""
    candle_limit = max(int(config.LIMIT_MA_PERIOD_MINUTES) + int(config.LIMIT_MA_EXTRA_CANDLES), 1)
    return get_minute_candles(client=client, symbol=symbol, limit=candle_limit)


def extract_tick_size_and_qty_step(
    instrument_info: dict[str, Any],
) -> tuple[float, float]:
    """Extract Bybit tick size and quantity step from instrument metadata.

    Bybit V5 linear instrument metadata normally stores price precision under
    priceFilter.tickSize and quantity precision under lotSizeFilter.qtyStep.
    Values usually arrive as strings and are converted to positive floats here.
    """
    price_filter = instrument_info.get("priceFilter")
    lot_size_filter = instrument_info.get("lotSizeFilter")
    if not isinstance(price_filter, dict):
        raise ValueError("Instrument metadata is missing priceFilter.")
    if not isinstance(lot_size_filter, dict):
        raise ValueError("Instrument metadata is missing lotSizeFilter.")

    tick_size = _to_positive_float(price_filter.get("tickSize"), "priceFilter.tickSize")
    qty_step = _to_positive_float(lot_size_filter.get("qtyStep"), "lotSizeFilter.qtyStep")
    return tick_size, qty_step


def _load_tick_size_and_qty_step(client: BybitClient, symbol: str) -> tuple[float, float]:
    """Load and parse instrument rounding metadata for one symbol."""
    instrument_info = get_instrument_info(client, symbol)
    if instrument_info is None:
        raise ValueError(f"Instrument metadata is unavailable for {symbol}.")
    return extract_tick_size_and_qty_step(instrument_info)


def _get_symbol_position_qty(client: BybitClient, symbol: str) -> float:
    """Read current signed position quantity for one symbol."""
    positions = get_current_positions(client, symbols=[symbol])
    return float(positions.get(symbol, 0.0))


def _cancel_orders(client: BybitClient, symbol: str) -> None:
    """Cancel all open orders for one symbol and log the intent."""
    _get_execution_logger().info("Canceling open orders for %s during limit rebalance.", symbol)
    cancel_all_orders_for_symbol(client, symbol)


def _summary(
    status: str,
    symbol: str,
    requested_qty_delta: float,
    target_position_qty: float | None,
    remaining_delta: float,
    orders_placed: int,
    iterations: int,
    error: str | None = None,
) -> dict[str, Any]:
    """Build a consistent rebalance summary dictionary."""
    summary: dict[str, Any] = {
        "status": status,
        "symbol": symbol,
        "requested_qty_delta": requested_qty_delta,
        "target_position_qty": target_position_qty,
        "remaining_delta": remaining_delta,
        "orders_placed": orders_placed,
        "iterations": iterations,
    }
    if error is not None:
        summary["error"] = error
    return summary


def _is_timeout_enabled() -> bool:
    """Return True when maximum rebalance duration is active."""
    return config.ENABLE_MAX_REBALANCE_DURATION == 1


def _sleep_check_interval() -> None:
    """Sleep until the next limit rebalance check."""
    _sleep(float(config.LIMIT_ORDER_CHECK_INTERVAL_SECONDS))


def _sleep(seconds: float) -> None:
    """Sleep helper kept patchable for tests."""
    time.sleep(seconds)


def _now_seconds() -> float:
    """Return monotonic time in seconds, kept patchable for tests."""
    return time.monotonic()


def _to_float(value: Any) -> float | None:
    """Convert a value to float without raising."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_positive_float(value: Any, field_name: str) -> float:
    """Convert a metadata field to a positive float or raise ValueError."""
    converted = _to_float(value)
    if converted is None or converted <= 0:
        raise ValueError(f"Instrument metadata field {field_name} is missing or invalid.")
    return converted


def _get_execution_logger() -> logging.Logger:
    """Return the configured execution logger."""
    return get_loggers()["execution"]
