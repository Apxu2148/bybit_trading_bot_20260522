from __future__ import annotations

import json
from pathlib import Path

from pytest import MonkeyPatch

from state import state_manager


REQUIRED_STATE_KEYS = {
    "rebalance_equity",
    "max_total_equity_seen",
    "last_rebalance_timestamp",
    "rebalance_timestamps",
    "mode",
    "last_selected_symbol",
    "last_error",
}


def test_default_state_contains_required_keys() -> None:
    default_state = state_manager.get_default_state()

    assert REQUIRED_STATE_KEYS.issubset(default_state)
    assert default_state["mode"] == "normal"


def test_load_state_creates_state_file_if_missing(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    state_file = tmp_path / "nested" / "bot_state.json"
    monkeypatch.setattr(state_manager, "STATE_FILE_PATH", state_file)

    loaded_state = state_manager.load_state()

    assert state_file.exists()
    assert REQUIRED_STATE_KEYS.issubset(loaded_state)
    assert json.loads(state_file.read_text(encoding="utf-8"))["mode"] == "normal"


def test_save_state_writes_valid_pretty_json(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    state_file = tmp_path / "bot_state.json"
    monkeypatch.setattr(state_manager, "STATE_FILE_PATH", state_file)

    state_manager.save_state({"mode": "test", "last_error": "Ошибка"})

    raw_text = state_file.read_text(encoding="utf-8")
    assert "\n  " in raw_text
    assert "Ошибка" in raw_text
    assert json.loads(raw_text) == {"mode": "test", "last_error": "Ошибка"}


def test_load_state_reads_json(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    state_file = tmp_path / "bot_state.json"
    monkeypatch.setattr(state_manager, "STATE_FILE_PATH", state_file)
    state_manager.save_state({"mode": "loaded", "last_error": "none"})

    loaded_state = state_manager.load_state()

    assert loaded_state["mode"] == "loaded"
    assert loaded_state["last_error"] == "none"


def test_update_state_updates_only_provided_keys_and_preserves_others(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    state_file = tmp_path / "bot_state.json"
    monkeypatch.setattr(state_manager, "STATE_FILE_PATH", state_file)
    state_manager.save_state(
        {
            "mode": "normal",
            "last_error": "keep me",
            "last_selected_symbol": None,
        }
    )

    updated_state = state_manager.update_state({"last_selected_symbol": "BTCUSDT"})

    assert updated_state["mode"] == "normal"
    assert updated_state["last_error"] == "keep me"
    assert updated_state["last_selected_symbol"] == "BTCUSDT"
    assert json.loads(state_file.read_text(encoding="utf-8"))["last_selected_symbol"] == "BTCUSDT"


def test_reset_state_restores_default_state(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    state_file = tmp_path / "bot_state.json"
    monkeypatch.setattr(state_manager, "STATE_FILE_PATH", state_file)
    state_manager.save_state({"mode": "changed", "last_selected_symbol": "BTCUSDT"})

    reset = state_manager.reset_state()

    assert reset == state_manager.get_default_state()
    assert json.loads(state_file.read_text(encoding="utf-8")) == state_manager.get_default_state()


def test_load_state_recreates_corrupted_json(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    state_file = tmp_path / "bot_state.json"
    monkeypatch.setattr(state_manager, "STATE_FILE_PATH", state_file)
    state_file.write_text("{not valid json", encoding="utf-8")

    loaded_state = state_manager.load_state()

    assert REQUIRED_STATE_KEYS.issubset(loaded_state)
    assert loaded_state == state_manager.get_default_state()
    assert json.loads(state_file.read_text(encoding="utf-8"))["mode"] == "normal"
    assert list(tmp_path.glob("bot_state.json.corrupted.*"))
