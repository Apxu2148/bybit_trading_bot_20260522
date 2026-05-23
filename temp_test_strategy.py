"""Temporary manual read-only check for the Stage 5 strategy pipeline."""

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
from market_data.candles import get_hourly_candles
from market_data.filters import get_eligible_symbols
from market_data.instruments import get_usdt_perpetual_symbols
from strategy.loader import get_target_leverage_function
from strategy.momentum_volatility import rank_symbols


def main() -> None:
    """Run the read-only market data, filter, and strategy pipeline."""
    print("Temporary Stage 5 strategy check")
    print("=" * 80)
    print("This script uses public market data only and does not place orders.\n")

    client = BybitClient()

    try:
        symbols = get_usdt_perpetual_symbols(client)
    except Exception as exc:
        print(f"Symbol loading failed: {exc.__class__.__name__}: {exc}")
        return

    print(f"Total USDT perpetual symbol count: {len(symbols)}")

    try:
        eligible_symbols = get_eligible_symbols(client, symbols)
    except Exception as exc:
        print(f"Filtering failed: {exc.__class__.__name__}: {exc}")
        return

    print(f"Eligible symbol count: {len(eligible_symbols)}")

    candles_by_symbol = _load_hourly_candles(client, eligible_symbols)
    ranked_symbols = rank_symbols(
        eligible_symbols=eligible_symbols,
        candles_by_symbol=candles_by_symbol,
    )

    print("\nTop ranked symbols:")
    pprint(ranked_symbols[:10])

    try:
        calculate_target_leverage = get_target_leverage_function(config.TARGET_LEVERAGE_MODULE)
        target_leverage = calculate_target_leverage(
            eligible_symbols=eligible_symbols,
            candles_by_symbol=candles_by_symbol,
        )
    except Exception as exc:
        print(f"Strategy calculation failed: {exc.__class__.__name__}: {exc}")
        return

    print("\nFinal target leverage dict:")
    pprint(target_leverage)
    print("\nNo orders, leverage changes, or private account calls were made.")


def _load_hourly_candles(
    client: BybitClient,
    eligible_symbols: list[str],
) -> dict[str, list[dict[str, Any]]]:
    """Load hourly candles for eligible symbols using the Stage 4 candle helper."""
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


if __name__ == "__main__":
    main()
