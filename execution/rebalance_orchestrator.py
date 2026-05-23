"""High-level rebalance orchestration from target leverage to execution."""

from __future__ import annotations

import logging
from typing import Any

from bybit.client import BybitClient
from config import config
from execution.cleanup import cleanup_small_positions
from execution.limit_rebalancer import rebalance_by_limit_order
from execution.orders import cancel_all_orders_for_symbol
from logging_setup.logger import get_loggers
from market_data.candles import get_hourly_candles, get_last_close
from portfolio.positions import get_current_positions, get_exchange_equity, get_total_equity
from portfolio.rebalance_plan import build_rebalance_plan


def run_rebalance(
    client: BybitClient,
    target_leverage: dict[str, float],
) -> dict[str, Any]:
    """Build and execute a full rebalance from target leverage."""
    logger = _get_execution_logger()
    logger.info("Rebalance orchestration started.")
    logger.info("Target leverage: %s.", target_leverage)

    try:
        exchange_equity = get_exchange_equity(client)
        total_equity = get_total_equity(exchange_equity)
        current_positions = get_current_positions(client)
        symbols = get_symbols_for_rebalance(current_positions, target_leverage)
    except Exception as exc:
        logger.error("Critical rebalance setup failed; error_type=%s.", exc.__class__.__name__)
        return _build_summary(
            status="failed",
            exchange_equity=0.0,
            total_equity=0.0,
            current_positions={},
            target_leverage=target_leverage,
            target_positions={},
            delta_qty={},
            execution_results={"error": f"{exc.__class__.__name__}: {exc}"},
            cleanup_result=None,
        )

    logger.info("Exchange equity: %s.", exchange_equity)
    logger.info("Reserve balance: %s.", config.RESERVE_BALANCE_USDT)
    logger.info("Total equity: %s.", total_equity)
    logger.info("Current positions: %s.", current_positions)

    if not symbols:
        logger.info("No current positions or target leverage; rebalance has no action.")
        return _build_summary(
            status="no_action",
            exchange_equity=exchange_equity,
            total_equity=total_equity,
            current_positions=current_positions,
            target_leverage=target_leverage,
            target_positions={},
            delta_qty={},
            execution_results={},
            cleanup_result=None,
        )

    try:
        last_close_prices = build_last_close_prices_for_symbols(client, symbols)
        plan = build_rebalance_plan(
            current_positions=current_positions,
            target_leverage=target_leverage,
            total_equity=total_equity,
            last_close_prices=last_close_prices,
        )
    except Exception as exc:
        logger.error("Rebalance plan build failed; error_type=%s.", exc.__class__.__name__)
        return _build_summary(
            status="failed",
            exchange_equity=exchange_equity,
            total_equity=total_equity,
            current_positions=current_positions,
            target_leverage=target_leverage,
            target_positions={},
            delta_qty={},
            execution_results={"error": f"{exc.__class__.__name__}: {exc}"},
            cleanup_result=None,
        )

    target_positions = plan["target_positions"]
    delta_qty = plan["delta_qty"]
    current_aligned = plan["current_positions_aligned"]
    target_aligned = plan["target_positions_aligned"]
    plan_symbols = sorted(delta_qty)

    logger.info("Target positions: %s.", target_positions)
    logger.info("Delta qty: %s.", delta_qty)

    _cancel_symbols(client, plan_symbols)
    execution_results = execute_delta_plan(
        client=client,
        delta_qty=delta_qty,
        current_positions=current_aligned,
        target_positions=target_aligned,
    )
    _cancel_symbols(client, plan_symbols)

    executable_deltas = {
        symbol: delta
        for symbol, delta in delta_qty.items()
        if delta != 0
    }
    if not executable_deltas:
        status = "no_action"
    elif any(_execution_failed(result) for result in execution_results.values()):
        status = "partial_failed"
    else:
        status = "completed"

    cleanup_result = None
    if config.ENABLE_SMALL_POSITION_CLEANUP == 1:
        refreshed_positions = get_current_positions(client)
        cleanup_symbols = sorted(set(refreshed_positions) | set(plan_symbols))
        cleanup_positions = {
            symbol: refreshed_positions.get(symbol, 0.0)
            for symbol in cleanup_symbols
            if refreshed_positions.get(symbol, 0.0) != 0
        }
        cleanup_prices = {
            symbol: price
            for symbol, price in last_close_prices.items()
            if symbol in cleanup_symbols
        }
        cleanup_result = cleanup_small_positions(
            client=client,
            current_positions=cleanup_positions,
            last_close_prices=cleanup_prices,
        )
        logger.info("Cleanup result: %s.", cleanup_result)
    else:
        logger.info("Small-position cleanup is disabled.")

    logger.info("Rebalance orchestration finished with status=%s.", status)
    return _build_summary(
        status=status,
        exchange_equity=exchange_equity,
        total_equity=total_equity,
        current_positions=current_positions,
        target_leverage=target_leverage,
        target_positions=target_positions,
        delta_qty=delta_qty,
        execution_results=execution_results,
        cleanup_result=cleanup_result,
    )


def get_symbols_for_rebalance(
    current_positions: dict[str, float],
    target_leverage: dict[str, float],
) -> list[str]:
    """Return sorted symbols required by current positions or targets."""
    return sorted(set(current_positions) | set(target_leverage))


def build_last_close_prices_for_symbols(
    client: BybitClient,
    symbols: list[str],
) -> dict[str, float]:
    """Build last-close prices for symbols using hourly candles."""
    logger = _get_execution_logger()
    last_close_prices: dict[str, float] = {}
    candle_limit = max(int(config.SCORE_LOOKBACK_HOURS) + 1, 1)

    for symbol in symbols:
        try:
            candles = get_hourly_candles(client=client, symbol=symbol, limit=candle_limit)
            last_close = get_last_close(candles)
        except Exception as exc:
            logger.warning("Could not load last close for %s; error_type=%s.", symbol, exc.__class__.__name__)
            continue

        if last_close is None or last_close <= 0:
            logger.warning("Skipping last close for %s because it is unavailable or invalid.", symbol)
            continue

        last_close_prices[symbol] = last_close

    return last_close_prices


def should_prepare_leverage(
    current_position_qty: float,
    target_position_qty: float,
) -> bool:
    """Return True when target absolute exposure is greater than current."""
    return abs(target_position_qty) > abs(current_position_qty)


def execute_delta_plan(
    client: BybitClient,
    delta_qty: dict[str, float],
    current_positions: dict[str, float],
    target_positions: dict[str, float],
) -> dict[str, Any]:
    """Execute non-zero delta quantities sequentially through the rebalancer."""
    logger = _get_execution_logger()
    execution_results: dict[str, Any] = {}

    for symbol, delta in delta_qty.items():
        if delta == 0:
            execution_results[symbol] = {"status": "skipped", "reason": "zero_delta"}
            continue

        current_qty = current_positions.get(symbol, 0.0)
        target_qty = target_positions.get(symbol, 0.0)
        prepare_leverage = should_prepare_leverage(current_qty, target_qty)
        logger.info(
            "Executing delta for %s; delta=%s prepare_leverage=%s.",
            symbol,
            delta,
            prepare_leverage,
        )

        try:
            result = rebalance_by_limit_order(
                client=client,
                symbol=symbol,
                qty_delta=delta,
                prepare_leverage=prepare_leverage,
            )
            execution_results[symbol] = result
            logger.info("Execution result for %s: %s.", symbol, result)
        except Exception as exc:
            execution_results[symbol] = {
                "status": "failed",
                "error": f"{exc.__class__.__name__}: {exc}",
            }
            logger.error("Execution failed for %s; error_type=%s.", symbol, exc.__class__.__name__)

    return execution_results


def _cancel_symbols(client: BybitClient, symbols: list[str]) -> None:
    """Cancel all open orders for symbols, logging failures and continuing."""
    logger = _get_execution_logger()
    for symbol in symbols:
        try:
            logger.info("Canceling open orders for %s in rebalance orchestrator.", symbol)
            cancel_all_orders_for_symbol(client, symbol)
        except Exception as exc:
            logger.warning("Cancel-all failed for %s; error_type=%s.", symbol, exc.__class__.__name__)


def _execution_failed(result: Any) -> bool:
    """Return True when an execution result represents failure."""
    return isinstance(result, dict) and result.get("status") in {"failed", "timeout"}


def _build_summary(
    status: str,
    exchange_equity: float,
    total_equity: float,
    current_positions: dict[str, float],
    target_leverage: dict[str, float],
    target_positions: dict[str, float],
    delta_qty: dict[str, float],
    execution_results: dict[str, Any],
    cleanup_result: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build the public rebalance orchestration summary."""
    return {
        "status": status,
        "exchange_equity": exchange_equity,
        "reserve_balance": float(config.RESERVE_BALANCE_USDT),
        "total_equity": total_equity,
        "current_positions": current_positions,
        "target_leverage": target_leverage,
        "target_positions": target_positions,
        "delta_qty": delta_qty,
        "execution_results": execution_results,
        "cleanup_result": cleanup_result,
    }


def _get_execution_logger() -> logging.Logger:
    """Return the configured execution logger."""
    return get_loggers()["execution"]
