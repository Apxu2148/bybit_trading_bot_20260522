"""Temporary optional live test for one local bot-loop iteration.

This script can place real orders through the normal Stage 9 bot logic when a
rebalance trigger fires. It is isolated from pytest and requires exact typed
confirmation before it calls run_once().
"""

from __future__ import annotations

import sys
from pathlib import Path
from pprint import pprint

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from bot_loop import run_once
from bybit.client import BybitClient
from state.state_manager import load_state

CONFIRMATION_TEXT = "YES_RUN_ONCE_REAL_BOT_LOGIC"


def main() -> None:
    """Run one manually confirmed live bot-loop iteration."""
    print("TEMPORARY LIVE RUN-ONCE BOT LOGIC TEST")
    print("=" * 80)
    print("WARNING: this script may place real orders on the configured Bybit account.")
    print("It calls the same run_once() function used by python main.py.")
    print("A rebalance may run if RUN_REBALANCE_ON_START is enabled or the equity threshold is reached.")
    print("This script is not called by pytest or main.py.")
    print()

    confirmation = input(f"Type exactly {CONFIRMATION_TEXT} to continue: ").strip()
    if confirmation != CONFIRMATION_TEXT:
        print("Confirmation did not match. Exiting without running bot logic.")
        return

    client = BybitClient()
    state = load_state()

    try:
        updated_state = run_once(client, state)
    except KeyboardInterrupt:
        print("\nInterrupted by user during run_once(). Manual account review may be required.")
        return
    except Exception as exc:
        print(f"run_once() failed: {exc.__class__.__name__}: {exc}")
        return

    print("\nReturned state:")
    pprint(updated_state)


if __name__ == "__main__":
    main()
