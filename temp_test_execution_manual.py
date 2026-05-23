"""Temporary optional live execution check.

This script can place real orders. It is isolated from pytest and the normal
bot entry point, and it requires an exact typed confirmation before doing
anything live.
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
from execution.orders import place_market_order
from market_data.instruments import get_instrument_info
from utils.rounding import round_qty_abs_down

CONFIRMATION_TEXT = "YES_PLACE_TEST_ORDER"
DEFAULT_SYMBOL = "DOGEUSDT"
TEST_NOTIONAL_USDT = 10.0


def main() -> None:
    """Run an optional live order open-and-close check after confirmation."""
    print("TEMPORARY LIVE EXECUTION TEST")
    print("=" * 80)
    print("WARNING: this script may place real orders on the configured Bybit account.")
    print("It will attempt to open about 10 USDT notional and then close the same quantity.")
    print("It does not run from pytest or main.py.")
    print(f"Default symbol: {DEFAULT_SYMBOL}")
    print()

    confirmation = input(f"Type exactly {CONFIRMATION_TEXT} to continue: ").strip()
    if confirmation != CONFIRMATION_TEXT:
        print("Confirmation did not match. Exiting without placing any orders.")
        return

    client = BybitClient()
    symbol = DEFAULT_SYMBOL

    try:
        last_price = _get_last_price(client, symbol)
        qty_step = _get_qty_step(client, symbol)
        qty = round_qty_abs_down(TEST_NOTIONAL_USDT / last_price, qty_step)
    except Exception as exc:
        print(f"Could not prepare test order: {exc.__class__.__name__}: {exc}")
        return

    if qty <= 0:
        print("Rounded test quantity is zero. Exiting without placing orders.")
        return

    print(f"Prepared test order: symbol={symbol}, last_price={last_price}, qty={qty}")
    print("Placing market Buy order...")

    opened = False
    try:
        open_response = place_market_order(client=client, symbol=symbol, qty=qty, reduce_only=False)
        opened = True
        print("Open response:")
        pprint(open_response)
    except Exception as exc:
        print(f"Open order failed: {exc.__class__.__name__}: {exc}")

    if not opened:
        print("Open order was not accepted. No close order will be sent.")
        return

    print("\nAttempting to close the same quantity with reduce_only=True...")
    try:
        close_response = place_market_order(client=client, symbol=symbol, qty=-qty, reduce_only=True)
        print("Close response:")
        pprint(close_response)
    except Exception as exc:
        print(f"Close order failed: {exc.__class__.__name__}: {exc}")
        print("Manual account review may be required.")


def _get_last_price(client: BybitClient, symbol: str) -> float:
    """Read last traded price from Bybit public ticker data."""
    response = client.get_tickers(category="linear", symbol=symbol)
    for ticker in _extract_result_list(response):
        if isinstance(ticker, dict) and ticker.get("symbol") == symbol:
            last_price = _to_float(ticker.get("lastPrice"))
            if last_price is not None and last_price > 0:
                return last_price
    raise ValueError(f"Could not read a valid last price for {symbol}.")


def _get_qty_step(client: BybitClient, symbol: str) -> float:
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


def _extract_result_list(response: Any) -> list[Any]:
    """Extract a Bybit V5 result.list payload safely."""
    if not isinstance(response, dict):
        return []
    result = response.get("result")
    if not isinstance(result, dict):
        return []
    rows = result.get("list")
    return rows if isinstance(rows, list) else []


def _to_float(value: Any) -> float | None:
    """Convert a value to float without raising."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


if __name__ == "__main__":
    main()
