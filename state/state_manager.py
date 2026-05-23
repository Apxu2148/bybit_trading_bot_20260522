"""Minimal JSON state manager for runtime bot state.

The bot will eventually need to remember runtime values between process
restarts. The state manager stores a small JSON document in state/bot_state.json
and keeps the behavior intentionally conservative:

* If the state file does not exist, it is created from defaults.
* If the file is corrupted or does not contain a JSON object, it is recreated.
* Updates are merged into the current state and saved immediately.

This module must only read and write the external state JSON file. It must not
embed balances, positions, or logs in code. Later modules can decide which
runtime values should be placed into the state dictionary.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import config

STATE_FILE_PATH = Path(config.STATE_FILE)


def get_default_state() -> dict[str, Any]:
    """Return a fresh default runtime state dictionary.

    State fields:
        rebalance_equity: Account equity snapshot recorded around rebalance time.
        max_total_equity_seen: Highest total equity observed by future risk logic.
        last_rebalance_timestamp: UTC timestamp of the last completed rebalance.
        rebalance_timestamps: UTC timestamps used for future frequency limits.
        mode: Runtime mode marker. Stage 2 uses "normal" by default.
        last_selected_symbol: Symbol most recently selected by future strategy code.
        last_error: Last high-level runtime error message, if any.
        next_strategy_check_timestamp: UTC timestamp before the next market scan.
        last_total_equity: Most recent total equity observed by the local loop.
        last_rebalance_status: Status returned by the latest rebalance attempt.
    """
    return {
        # Account equity snapshot recorded around rebalance time.
        "rebalance_equity": None,
        # Highest total equity seen by future risk-control logic.
        "max_total_equity_seen": None,
        # UTC timestamp of the last completed rebalance.
        "last_rebalance_timestamp": None,
        # Recent rebalance timestamps for future rate/frequency controls.
        "rebalance_timestamps": [],
        # Current runtime mode. Stage 2 defaults to normal infrastructure mode.
        "mode": "normal",
        # Last symbol selected by a future strategy module.
        "last_selected_symbol": None,
        # Last high-level runtime error message.
        "last_error": None,
        # UTC timestamp before another strategy check should run.
        "next_strategy_check_timestamp": None,
        # Most recent total equity observed by the bot loop.
        "last_total_equity": None,
        # Status returned by the latest rebalance attempt.
        "last_rebalance_status": None,
    }


def load_state() -> dict[str, Any]:
    """Load runtime state from JSON, creating or repairing the file if needed."""
    if not STATE_FILE_PATH.exists():
        state = get_default_state()
        save_state(state)
        return state

    try:
        raw_state = json.loads(STATE_FILE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _handle_corrupted_state(exc)
        state = get_default_state()
        save_state(state)
        return state

    if not isinstance(raw_state, dict):
        _handle_corrupted_state(ValueError("State JSON root must be an object"))
        state = get_default_state()
        save_state(state)
        return state

    state = get_default_state()
    state.update(raw_state)
    if set(get_default_state()) - set(raw_state):
        save_state(state)
    return state


def save_state(state: dict[str, Any]) -> None:
    """Persist runtime state to state/bot_state.json."""
    STATE_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = STATE_FILE_PATH.with_suffix(f"{STATE_FILE_PATH.suffix}.tmp")
    serialized = json.dumps(state, indent=2, ensure_ascii=False)
    try:
        temp_path.write_text(serialized, encoding="utf-8")
        temp_path.replace(STATE_FILE_PATH)
    except OSError:
        # Some Windows environments can deny atomic replacement inside synced or
        # sandboxed folders. Direct write is less atomic but still produces valid
        # JSON and keeps the bot operational.
        STATE_FILE_PATH.write_text(serialized, encoding="utf-8")
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


def update_state(updates: dict[str, Any]) -> dict[str, Any]:
    """Merge updates into current state, save it, and return the new state."""
    state = load_state()
    state.update(updates)
    save_state(state)
    return state


def reset_state() -> dict[str, Any]:
    """Replace current runtime state with default state and return it."""
    state = get_default_state()
    save_state(state)
    return state


def _handle_corrupted_state(error: Exception) -> None:
    """Preserve corrupted state if possible, then log a warning."""
    backup_path = _backup_corrupted_state()
    message = "Runtime state was corrupted and has been reset to defaults."
    if backup_path is not None:
        message = f"{message} Corrupted file backup: {backup_path}"
    _log_state_warning(message, error)


def _backup_corrupted_state() -> Path | None:
    """Move a corrupted state file aside so it can be inspected later."""
    if not STATE_FILE_PATH.exists():
        return None

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_path = STATE_FILE_PATH.with_name(f"{STATE_FILE_PATH.name}.corrupted.{timestamp}")
    try:
        STATE_FILE_PATH.replace(backup_path)
        return backup_path
    except OSError:
        return None


def _log_state_warning(message: str, error: Exception) -> None:
    """Log a state warning through the main logger if it has handlers."""
    logger = logging.getLogger("main")
    if logger.handlers:
        logger.warning("%s Error: %s", message, error)
