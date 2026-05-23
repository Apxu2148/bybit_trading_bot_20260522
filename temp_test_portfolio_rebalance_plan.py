"""Temporary manual read-only check for portfolio and rebalance planning."""

from __future__ import annotations

import sys
from pathlib import Path
from pprint import pprint
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from bybit.client import BybitClient
from config import config
from market_data.candles import get_hourly_candles, get_last_close
from market_data.filters import get_eligible_symbols
from market_data.instruments import get_usdt_perpetual_symbols
from portfolio.positions import get_current_positions, get_exchange_equity, get_total_equity
from portfolio.rebalance_plan import build_rebalance_plan
from strategy.loader import get_target_leverage_function


def main() -> None:
    """Run the read-only portfolio and rebalance-plan pipeline."""
    print("Temporary Stage 6 portfolio and rebalance-plan check")
    print("=" * 80)
    print("This script is read-only. It does not place orders, cancel orders, or change leverage.\n")

    client = BybitClient()

    exchange_equity = _read_exchange_equity(client)
    if exchange_equity is None:
        return

    total_equity = get_total_equity(exchange_equity)
    current_positions = _read_current_positions(client)
    if current_positions is None:
        return

    symbols = _load_symbols(client)
    if symbols is None:
        return

    eligible_symbols = _load_eligible_symbols(client, symbols)
    if eligible_symbols is None:
        return

    candles_by_symbol = _load_hourly_candles(client, eligible_symbols)
    last_close_prices = _build_last_close_prices(candles_by_symbol)

    target_leverage = _calculate_target_leverage(eligible_symbols, candles_by_symbol)
    if target_leverage is None:
        return

    rebalance_plan = build_rebalance_plan(
        current_positions=current_positions,
        target_leverage=target_leverage,
        total_equity=total_equity,
        last_close_prices=last_close_prices,
    )

    print("\nPortfolio summary")
    print("-" * 80)
    print(f"Exchange equity: {exchange_equity}")
    print(f"Reserve balance: {config.RESERVE_BALANCE_USDT}")
    print(f"Total equity: {total_equity}")

    print("\nCurrent positions:")
    pprint(current_positions)

    print("\nTarget leverage:")
    pprint(target_leverage)

    print("\nTarget positions:")
    pprint(rebalance_plan["target_positions"])

    print("\nDelta quantities:")
    pprint(rebalance_plan["delta_qty"])

    print("\nNo orders, cancellations, leverage changes, or position modifications were made.")


def _read_exchange_equity(client: BybitClient) -> float | None:
    """Read exchange equity and print a readable error if it fails."""
    try:
        return get_exchange_equity(client)
    except Exception as exc:
        print(f"Exchange equity read failed: {exc.__class__.__name__}: {exc}")
        return None


def _read_current_positions(client: BybitClient) -> dict[str, float] | None:
    """Read current positions and print a readable error if it fails."""
    try:
        return get_current_positions(client)
    except Exception as exc:
        print(f"Current position read failed: {exc.__class__.__name__}: {exc}")
        return None


def _load_symbols(client: BybitClient) -> list[str] | None:
    """Load active USDT perpetual symbols."""
    try:
        symbols = get_usdt_perpetual_symbols(client)
        print(f"Loaded {len(symbols)} USDT perpetual symbol(s).")
        return symbols
    except Exception as exc:
        print(f"Symbol loading failed: {exc.__class__.__name__}: {exc}")
        return None


def _load_eligible_symbols(client: BybitClient, symbols: list[str]) -> list[str] | None:
    """Run the Stage 4 filter pipeline."""
    try:
        eligible_symbols = get_eligible_symbols(client, symbols)
        print(f"Eligible symbol count: {len(eligible_symbols)}")
        return eligible_symbols
    except Exception as exc:
        print(f"Filtering failed: {exc.__class__.__name__}: {exc}")
        return None


def _load_hourly_candles(
    client: BybitClient,
    eligible_symbols: list[str],
) -> dict[str, list[dict[str, Any]]]:
    """Load hourly candles for eligible symbols."""
    candle_limit = max(int(config.SCORE_LOOKBACK_HOURS) + 1, 1)
    candles_by_symbol: dict[str, list[dict[str, Any]]] = {}

    for index, symbol in enumerate(eligible_symbols, start=1):
        try:
            candles_by_symbol[symbol] = get_hourly_candles(
                client=client,
                symbol=symbol,
                limit=candle_limit,
            )
            print(f"Loaded candles for {symbol} ({index}/{len(eligible_symbols)}).")
        except Exception as exc:
            print(f"Could not load candles for {symbol}: {exc.__class__.__name__}: {exc}")
            candles_by_symbol[symbol] = []

    return candles_by_symbol


def _build_last_close_prices(
    candles_by_symbol: dict[str, list[dict[str, Any]]],
) -> dict[str, float]:
    """Build a last-close price map from normalized candles."""
    last_close_prices: dict[str, float] = {}
    for symbol, candles in candles_by_symbol.items():
        last_close = get_last_close(candles)
        if last_close is not None:
            last_close_prices[symbol] = last_close
    return last_close_prices


def _calculate_target_leverage(
    eligible_symbols: list[str],
    candles_by_symbol: dict[str, list[dict[str, Any]]],
) -> dict[str, float] | None:
    """Calculate target leverage through the configured strategy module."""
    try:
        calculate_target_leverage = get_target_leverage_function(config.TARGET_LEVERAGE_MODULE)
        return calculate_target_leverage(
            eligible_symbols=eligible_symbols,
            candles_by_symbol=candles_by_symbol,
        )
    except Exception as exc:
        print(f"Target leverage calculation failed: {exc.__class__.__name__}: {exc}")
        return None


if __name__ == "__main__":
    main()
