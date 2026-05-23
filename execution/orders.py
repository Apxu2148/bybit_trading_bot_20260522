"""Low-level Bybit order helpers.

These helpers define order intent and call the project BybitClient boundary.
They are not called automatically by the bot.
"""

from __future__ import annotations

import logging
from typing import Any

from bybit.client import BybitClient
from logging_setup.logger import get_loggers


def qty_to_side(qty_delta: float) -> str:
    """Return Bybit side from signed quantity delta."""
    if qty_delta > 0:
        return "Buy"
    if qty_delta < 0:
        return "Sell"
    raise ValueError("Order quantity delta must not be zero.")


def place_limit_order(
    client: BybitClient,
    symbol: str,
    qty: float,
    price: float,
    reduce_only: bool = False,
) -> dict[str, Any]:
    """Place one linear limit order through BybitClient."""
    side = qty_to_side(qty)
    abs_qty = abs(float(qty))
    if price <= 0:
        raise ValueError("Limit order price must be greater than zero.")

    _get_execution_logger().info(
        "Placing limit order intent: symbol=%s side=%s qty=%s price=%s reduce_only=%s.",
        symbol,
        side,
        abs_qty,
        price,
        reduce_only,
    )
    response = client.place_order(
        category="linear",
        symbol=symbol,
        side=side,
        orderType="Limit",
        qty=_format_number(abs_qty),
        price=_format_number(price),
        timeInForce="GTC",
        reduceOnly=reduce_only,
    )
    return _as_response_dict(response)


def place_market_order(
    client: BybitClient,
    symbol: str,
    qty: float,
    reduce_only: bool = False,
) -> dict[str, Any]:
    """Place one linear market order through BybitClient."""
    side = qty_to_side(qty)
    abs_qty = abs(float(qty))

    _get_execution_logger().info(
        "Placing market order intent: symbol=%s side=%s qty=%s reduce_only=%s.",
        symbol,
        side,
        abs_qty,
        reduce_only,
    )
    response = client.place_order(
        category="linear",
        symbol=symbol,
        side=side,
        orderType="Market",
        qty=_format_number(abs_qty),
        reduceOnly=reduce_only,
    )
    return _as_response_dict(response)


def cancel_all_orders_for_symbol(
    client: BybitClient,
    symbol: str,
) -> dict[str, Any]:
    """Cancel all open linear orders for one symbol."""
    _get_execution_logger().info("Canceling all open orders for symbol=%s.", symbol)
    response = client.cancel_all_orders(category="linear", symbol=symbol)
    return _as_response_dict(response)


def get_open_orders_for_symbol(
    client: BybitClient,
    symbol: str,
) -> dict[str, Any]:
    """Get open linear orders for one symbol."""
    _get_execution_logger().info("Reading open orders for symbol=%s.", symbol)
    response = client.get_open_orders(category="linear", symbol=symbol)
    return _as_response_dict(response)


def _format_number(value: float) -> str:
    """Format a numeric order field without scientific notation."""
    return f"{value:.16f}".rstrip("0").rstrip(".")


def _as_response_dict(response: Any) -> dict[str, Any]:
    """Return response dictionaries unchanged and wrap unusual responses."""
    if isinstance(response, dict):
        return response
    return {"raw_response": response}


def _get_execution_logger() -> logging.Logger:
    """Return the configured execution logger."""
    return get_loggers()["execution"]
