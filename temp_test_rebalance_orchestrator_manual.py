"""Temporary optional live test for full rebalance orchestration.

This script can place real orders. It is isolated from pytest and main.py, and
requires explicit typed confirmations before each live rebalance step.
"""

from __future__ import annotations

import sys
from pathlib import Path
from pprint import pprint

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from bybit.client import BybitClient
from execution.rebalance_orchestrator import run_rebalance

OPEN_CONFIRMATION_TEXT = "YES_RUN_REBALANCE_ORCHESTRATOR_TEST"
CLOSE_CONFIRMATION_TEXT = "YES_CLOSE_TEST_POSITION"
DEFAULT_TARGET_LEVERAGE = {"DOGEUSDT": 0.2}


def main() -> None:
    """Run an optional live open-and-close orchestration test."""
    print("TEMPORARY LIVE REBALANCE ORCHESTRATOR TEST")
    print("=" * 80)
    print("WARNING: this script may place real orders on the configured Bybit account.")
    print("It first targets a small DOGEUSDT position, then can run target_leverage = {}.")
    print("The close step may close current positions found by the rebalance plan.")
    print("The MA limit rebalancer may wait several minutes. Press Ctrl+C to stop if needed.")
    print("This script is not called by pytest or main.py.")
    print(f"Open target leverage: {DEFAULT_TARGET_LEVERAGE}")
    print()

    confirmation = input(f"Type exactly {OPEN_CONFIRMATION_TEXT} to open the test target: ").strip()
    if confirmation != OPEN_CONFIRMATION_TEXT:
        print("Confirmation did not match. Exiting without running rebalance.")
        return

    client = BybitClient()

    try:
        open_summary = run_rebalance(client, DEFAULT_TARGET_LEVERAGE)
        print("\nOpen rebalance summary:")
        pprint(open_summary)
    except KeyboardInterrupt:
        print("\nInterrupted by user during open rebalance.")
        return
    except Exception as exc:
        print(f"Open rebalance failed: {exc.__class__.__name__}: {exc}")
        return

    print()
    close_confirmation = input(f"Type exactly {CLOSE_CONFIRMATION_TEXT} to run target_leverage={{}}: ").strip()
    if close_confirmation != CLOSE_CONFIRMATION_TEXT:
        print("Close confirmation did not match. Leaving current account state unchanged by this script.")
        return

    try:
        close_summary = run_rebalance(client, {})
        print("\nClose rebalance summary:")
        pprint(close_summary)
    except KeyboardInterrupt:
        print("\nInterrupted by user during close rebalance. Manual account review may be required.")
    except Exception as exc:
        print(f"Close rebalance failed: {exc.__class__.__name__}: {exc}")
        print("Manual account review may be required.")


if __name__ == "__main__":
    main()
