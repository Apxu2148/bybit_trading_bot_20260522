"""Local bot loop for equity-triggered rebalancing."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from bybit.client import BybitClient
from config import config
from execution.rebalance_orchestrator import run_rebalance
from logging_setup.logger import get_loggers, setup_loggers
from market_data.candles import get_hourly_candles
from market_data.filters import get_eligible_symbols
from market_data.instruments import get_usdt_perpetual_symbols
from portfolio.positions import get_exchange_equity, get_total_equity
from state.state_manager import load_state, save_state
from strategy.loader import get_target_leverage_function
from triggers.rebalance_trigger import (
    calculate_equity_change_pct,
    initialize_rebalance_equity_if_needed,
    record_successful_rebalance,
    should_rebalance,
)

BOT_LOOP_SLEEP_SECONDS = 60


def build_target_leverage_from_market(
    client: BybitClient,
) -> tuple[dict[str, float], str | None]:
    """Build target leverage from current public market data and strategy."""
    symbols = get_usdt_perpetual_symbols(client)
    eligible_symbols = get_eligible_symbols(client, symbols)
    if not eligible_symbols:
        return {}, None

    candle_limit = max(int(config.SCORE_LOOKBACK_HOURS) + 1, 1)
    candles_by_symbol: dict[str, list[dict[str, Any]]] = {}
    for symbol in eligible_symbols:
        candles_by_symbol[symbol] = get_hourly_candles(
            client=client,
            symbol=symbol,
            limit=candle_limit,
        )

    calculate_target_leverage = get_target_leverage_function(config.TARGET_LEVERAGE_MODULE)
    target_leverage = calculate_target_leverage(
        eligible_symbols=eligible_symbols,
        candles_by_symbol=candles_by_symbol,
    )
    selected_symbol = next(iter(target_leverage), None)
    return target_leverage, selected_symbol


def run_once(
    client: BybitClient,
    state: dict[str, Any],
) -> dict[str, Any]:
    """Run one local bot loop iteration and persist state."""
    logger = _get_main_logger()
    exchange_equity = get_exchange_equity(client)
    total_equity = get_total_equity(exchange_equity)
    state = initialize_rebalance_equity_if_needed(state, total_equity)
    rebalance_equity = float(state.get("rebalance_equity") or total_equity)
    equity_change_pct = calculate_equity_change_pct(total_equity, rebalance_equity)

    state["last_total_equity"] = total_equity
    state["max_total_equity_seen"] = _max_optional_float(state.get("max_total_equity_seen"), total_equity)

    logger.info(
        "Equity check: exchange_equity=%s reserve_balance=%s total_equity=%s "
        "rebalance_equity=%s equity_change_pct=%s mode=%s.",
        exchange_equity,
        config.RESERVE_BALANCE_USDT,
        total_equity,
        rebalance_equity,
        equity_change_pct,
        state.get("mode", "normal"),
    )

    if _strategy_check_is_delayed(state):
        save_state(state)
        return state

    run_on_start = _should_run_rebalance_on_start(state)
    threshold_triggered = should_rebalance(total_equity, rebalance_equity)
    if not (run_on_start or threshold_triggered):
        state["last_rebalance_status"] = "not_triggered"
        save_state(state)
        return state

    target_leverage, selected_symbol = build_target_leverage_from_market(client)
    rebalance_summary = run_rebalance(client, target_leverage)
    status = str(rebalance_summary.get("status", "failed"))
    state["last_rebalance_status"] = status

    if status in {"completed", "no_action"}:
        state = record_successful_rebalance(
            state=state,
            new_rebalance_equity=total_equity,
            selected_symbol=selected_symbol,
        )
        if not target_leverage and selected_symbol is None:
            state["mode"] = "waiting_for_eligible_symbols"
            state["next_strategy_check_timestamp"] = _next_strategy_check_timestamp()
        else:
            state["mode"] = "normal"
            state["next_strategy_check_timestamp"] = None
    else:
        state["last_error"] = str(rebalance_summary.get("execution_results", rebalance_summary))
        state["mode"] = "error"

    save_state(state)
    return state


def run_bot_loop() -> None:
    """Run the local bot loop until Ctrl+C stops it gracefully."""
    setup_loggers()
    logger = _get_main_logger()
    client = BybitClient()
    state = load_state()
    logger.info("Local bot loop started.")

    while True:
        try:
            state = run_once(client, state)
            _sleep(BOT_LOOP_SLEEP_SECONDS)
        except KeyboardInterrupt:
            logger.info("Local bot loop stopped by user.")
            return
        except Exception:
            logger.exception("Unexpected bot loop error; sleeping before retry.")
            _sleep(BOT_LOOP_SLEEP_SECONDS)


def _should_run_rebalance_on_start(state: dict[str, Any]) -> bool:
    """Return True when startup rebalance should run once."""
    return config.RUN_REBALANCE_ON_START == 1 and not state.get("last_rebalance_timestamp")


def _strategy_check_is_delayed(state: dict[str, Any]) -> bool:
    """Return True when no-eligible-symbol wait mode is still active."""
    if state.get("mode") != "waiting_for_eligible_symbols":
        return False

    next_timestamp = state.get("next_strategy_check_timestamp")
    if not isinstance(next_timestamp, str):
        return False

    parsed_timestamp = _parse_utc_timestamp(next_timestamp)
    if parsed_timestamp is None:
        return False

    return datetime.now(timezone.utc) < parsed_timestamp


def _next_strategy_check_timestamp() -> str:
    """Return the next UTC timestamp for a no-eligible-symbol strategy check."""
    minutes = max(float(config.NO_ELIGIBLE_SYMBOLS_RECHECK_INTERVAL_MINUTES), 0.0)
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()


def _parse_utc_timestamp(timestamp: str) -> datetime | None:
    """Parse an ISO timestamp as an aware UTC datetime."""
    try:
        parsed = datetime.fromisoformat(timestamp)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _max_optional_float(current_value: Any, observed_value: float) -> float:
    """Return the max of an optional numeric value and an observed float."""
    try:
        current_float = float(current_value)
    except (TypeError, ValueError):
        return float(observed_value)
    return max(current_float, float(observed_value))


def _sleep(seconds: float) -> None:
    """Sleep helper kept patchable for tests."""
    time.sleep(seconds)


def _get_main_logger() -> logging.Logger:
    """Return the configured main logger."""
    return get_loggers()["main"]
