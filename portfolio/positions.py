"""Read-only portfolio state helpers."""

from __future__ import annotations

import logging
from typing import Any

from bybit.client import BybitAPIRequestError, BybitClient
from config import config
from logging_setup.logger import get_loggers


def get_current_positions(
    client: BybitClient,
    symbols: list[str] | None = None,
) -> dict[str, float]:
    """Return current linear positions keyed by symbol.

    Quantities are positive for long positions and negative for short
    positions. Zero-size positions are excluded.
    """
    logger = _get_main_logger()
    try:
        response = client.get_positions(category="linear", settle_coin="USDT")
    except BybitAPIRequestError:
        logger.warning("Position request with settleCoin=USDT failed; retrying without settleCoin.")
        response = client.get_positions(category="linear", settle_coin=None)

    positions = parse_positions_response(response)
    if symbols is None:
        return positions

    allowed_symbols = {symbol.upper() for symbol in symbols}
    return {
        symbol: qty
        for symbol, qty in positions.items()
        if symbol.upper() in allowed_symbols
    }


def get_exchange_equity(
    client: BybitClient,
) -> float:
    """Read account equity from Bybit wallet balance."""
    response = client.get_wallet_balance(account_type="UNIFIED")
    equity = parse_wallet_balance_response(response)
    _get_main_logger().info("Exchange equity parsed: %s.", equity)
    return equity


def get_total_equity(
    exchange_equity: float,
    reserve_balance: float | None = None,
) -> float:
    """Return exchange equity plus reserve balance."""
    reserve = float(config.RESERVE_BALANCE_USDT if reserve_balance is None else reserve_balance)
    total_equity = float(exchange_equity) + reserve
    logger = _get_main_logger()
    logger.info("Reserve balance used: %s.", reserve)
    logger.info("Total equity calculated: %s.", total_equity)
    return total_equity


def parse_positions_response(
    response: dict[str, Any],
) -> dict[str, float]:
    """Parse Bybit V5 positions into signed project quantities."""
    logger = _get_main_logger()
    positions: dict[str, float] = {}

    for raw_position in _extract_result_list(response, "positions"):
        if not isinstance(raw_position, dict):
            logger.warning("Skipping malformed position row; row_type=%s.", type(raw_position).__name__)
            continue

        symbol = raw_position.get("symbol")
        if not isinstance(symbol, str) or not symbol:
            logger.warning("Skipping malformed position with missing symbol.")
            continue

        size = _to_float(raw_position.get("size"))
        if size is None:
            logger.warning("Skipping position for %s because size is malformed.", symbol)
            continue
        if size == 0:
            continue

        signed_qty = _signed_position_qty(raw_position, abs(size), symbol)
        if signed_qty is None:
            continue

        positions[symbol] = positions.get(symbol, 0.0) + signed_qty

    return {
        symbol: qty
        for symbol, qty in positions.items()
        if qty != 0
    }


def parse_wallet_balance_response(
    response: dict[str, Any],
) -> float:
    """Parse Bybit wallet balance response into account equity."""
    logger = _get_main_logger()
    accounts = _extract_result_list(response, "wallet balance")

    for account in accounts:
        if not isinstance(account, dict):
            logger.warning("Skipping malformed wallet account row; row_type=%s.", type(account).__name__)
            continue

        total_equity = _to_float(account.get("totalEquity"))
        if total_equity is not None:
            return total_equity

    for account in accounts:
        if not isinstance(account, dict):
            continue

        coin_equity = _extract_usdt_coin_equity(account)
        if coin_equity is not None:
            return coin_equity

    logger.warning("Wallet balance response did not contain parseable equity.")
    return 0.0


def _extract_usdt_coin_equity(account: dict[str, Any]) -> float | None:
    """Return USDT coin equity or USD value from a wallet account row."""
    logger = _get_main_logger()
    coins = account.get("coin")
    if not isinstance(coins, list):
        return None

    for coin in coins:
        if not isinstance(coin, dict):
            logger.warning("Skipping malformed wallet coin row; row_type=%s.", type(coin).__name__)
            continue

        if coin.get("coin") != "USDT":
            continue

        for key in ("equity", "usdValue"):
            value = _to_float(coin.get(key))
            if value is not None:
                return value

    return None


def _signed_position_qty(
    raw_position: dict[str, Any],
    absolute_size: float,
    symbol: str,
) -> float | None:
    """Return signed position quantity based on Bybit side field."""
    logger = _get_main_logger()
    side = raw_position.get("side")
    if side == "Buy":
        return absolute_size
    if side == "Sell":
        return -absolute_size

    logger.warning("Skipping position for %s because side is missing or unsupported.", symbol)
    return None


def _extract_result_list(response: dict[str, Any], label: str) -> list[Any]:
    """Extract a Bybit V5 result.list payload safely."""
    logger = _get_main_logger()
    if not isinstance(response, dict):
        logger.warning("Skipping %s response; response_type=%s.", label, type(response).__name__)
        return []

    result = response.get("result")
    if not isinstance(result, dict):
        logger.warning("Skipping %s response with missing result object.", label)
        return []

    rows = result.get("list")
    if not isinstance(rows, list):
        logger.warning("Skipping %s response with missing result list.", label)
        return []

    return rows


def _to_float(value: Any) -> float | None:
    """Convert a value to float without raising."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _get_main_logger() -> logging.Logger:
    """Return the configured main logger."""
    return get_loggers()["main"]
