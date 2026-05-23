"""Temporary optional live test for the MA limit rebalancer.

This script can place real orders. It is isolated from pytest and main.py, and
requires exact typed confirmation before it calls the rebalancer.
"""

from __future__ import annotations

import sys
from pathlib import Path
from pprint import pprint
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from bybit.client import BybitClient
from execution.limit_rebalancer import rebalance_by_limit_order
from market_data.candles import get_last_close, get_minute_candles
from market_data.instruments import get_instrument_info
from utils.rounding import round_qty_abs_down

CONFIRMATION_TEXT = "YES_RUN_LIMIT_REBALANCER_TEST"
DEFAULT_SYMBOL = "DOGEUSDT"
TEST_NOTIONAL_USDT = 10.0


def main() -> None:
    """Run a manual open-and-close test through the MA limit rebalancer."""
    print("TEMPORARY LIVE MA LIMIT REBALANCER TEST")
    print("=" * 80)
    print("WARNING: this script may place real orders on the configured Bybit account.")
    print("It will attempt to open about 10 USDT notional, then close the same quantity.")
    print("The MA condition may take several minutes. Press Ctrl+C to stop if needed.")
    print("This script is not called by pytest or main.py.")
    print(f"Default symbol: {DEFAULT_SYMBOL}")
    print()

    confirmation = input(f"Type exactly {CONFIRMATION_TEXT} to continue: ").strip()
    if confirmation != CONFIRMATION_TEXT:
        print("Confirmation did not match. Exiting without placing any orders.")
        return

    client = BybitClient()
    symbol = DEFAULT_SYMBOL

    try:
        last_close = _read_last_close(client, symbol)
        qty_step = _read_qty_step(client, symbol)
        qty_delta = round_qty_abs_down(TEST_NOTIONAL_USDT / last_close, qty_step)
    except Exception as exc:
        print(f"Could not prepare limit rebalancer test: {exc.__class__.__name__}: {exc}")
        return

    if qty_delta <= 0:
        print("Rounded quantity is zero. Exiting without placing orders.")
        return

    print(f"Prepared test: symbol={symbol}, last_close={last_close}, qty_delta={qty_delta}")
    print("\nOpening position through rebalance_by_limit_order...")

    try:
        open_summary = rebalance_by_limit_order(client, symbol, qty_delta)
        print("Open summary:")
        pprint(open_summary)
    except KeyboardInterrupt:
        print("\nInterrupted by user during opening rebalance.")
        return
    except Exception as exc:
        print(f"Opening rebalance failed: {exc.__class__.__name__}: {exc}")
        return

    print("\nClosing same quantity through rebalance_by_limit_order...")
    try:
        close_summary = rebalance_by_limit_order(client, symbol, -qty_delta)
        print("Close summary:")
        pprint(close_summary)
    except KeyboardInterrupt:
        print("\nInterrupted by user during closing rebalance. Manual account review may be required.")
    except Exception as exc:
        print(f"Closing rebalance failed: {exc.__class__.__name__}: {exc}")
        print("Manual account review may be required.")


def _read_last_close(client: BybitClient, symbol: str) -> float:
    """Read the latest usable one-minute close for a symbol."""
    candles = get_minute_candles(client=client, symbol=symbol, limit=10)
    last_close = get_last_close(candles)
    if last_close is None or last_close <= 0:
        raise ValueError(f"Could not read a valid last close for {symbol}.")
    return last_close


def _read_qty_step(client: BybitClient, symbol: str) -> float:
    """Read quantity step from Bybit public instrument metadata."""
    instrument_info = get_instrument_info(client, symbol)
    if instrument_info is None:
        raise ValueError(f"Could not read instrument info for {symbol}.")

    lot_size_filter = instrument_info.get("lotSizeFilter")
    if not isinstance(lot_size_filter, dict):
        raise ValueError(f"Instrument info for {symbol} does not contain lotSizeFilter.")

    qty_step = _to_float(lot_size_filter.get("qtyStep"))
    if qty_step is None or qty_step <= 0:
        raise ValueError(f"Instrument info for {symbol} does not contain a valid qtyStep.")
    return qty_step


def _to_float(value: Any) -> float | None:
    """Convert a value to float without raising."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


if __name__ == "__main__":
    main()
