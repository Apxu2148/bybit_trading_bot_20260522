"""Temporary read-only manual check for Bybit instrument pagination."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from bybit.client import BybitClient
from market_data.instruments import get_usdt_perpetual_symbols


def main() -> None:
    """Load all USDT perpetual symbols and print pagination sanity checks."""
    print("Temporary Bybit instruments pagination check")
    print("=" * 80)
    print("This script uses public market data only and does not place orders.\n")

    client = BybitClient()

    try:
        symbols = get_usdt_perpetual_symbols(client)
    except Exception as exc:
        print(f"Instrument loading failed: {exc.__class__.__name__}: {exc}")
        return

    print(f"Total USDT perpetual symbol count: {len(symbols)}")
    print(f"First 20 symbols: {symbols[:20]}")
    print(f"Last 20 symbols: {symbols[-20:]}")
    print()

    for prefix in ("S", "T", "X", "Z"):
        has_prefix = any(symbol.startswith(prefix) for symbol in symbols)
        print(f"Symbols starting with {prefix}: {has_prefix}")

    print("\nNo orders, private calls, or leverage changes were made.")


if __name__ == "__main__":
    main()
