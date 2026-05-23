from __future__ import annotations

from typing import Any

from pytest import MonkeyPatch

from config import config
import bot_loop


class FakeClient:
    """Placeholder client for bot loop tests."""


class FakeLogger:
    """Small logger stand-in used by run_bot_loop tests."""

    def __init__(self) -> None:
        self.messages: list[str] = []

    def info(self, message: str, *args: Any) -> None:
        self.messages.append(message % args if args else message)

    def exception(self, message: str, *args: Any) -> None:
        self.messages.append(message % args if args else message)


def _patch_common_run_once_dependencies(monkeypatch: MonkeyPatch, total_equity: float) -> dict[str, Any]:
    calls: dict[str, Any] = {
        "saved": [],
        "build": 0,
        "rebalance": [],
    }
    monkeypatch.setattr(bot_loop, "get_exchange_equity", lambda client: total_equity - 40.0)
    monkeypatch.setattr(bot_loop, "get_total_equity", lambda exchange_equity: total_equity)
    monkeypatch.setattr(bot_loop, "save_state", lambda state: calls["saved"].append(dict(state)))
    monkeypatch.setattr(config, "RESERVE_BALANCE_USDT", 40.0)
    monkeypatch.setattr(config, "REBALANCE_THRESHOLD_PCT", 0.05)
    monkeypatch.setattr(config, "RUN_REBALANCE_ON_START", 0)
    monkeypatch.setattr(config, "NO_ELIGIBLE_SYMBOLS_RECHECK_INTERVAL_MINUTES", 60)

    def fake_build_target_leverage_from_market(client: FakeClient) -> tuple[dict[str, float], str | None]:
        calls["build"] += 1
        return {"DOGEUSDT": 1.0}, "DOGEUSDT"

    def fake_run_rebalance(client: FakeClient, target_leverage: dict[str, float]) -> dict[str, Any]:
        calls["rebalance"].append(target_leverage)
        return {"status": "completed"}

    monkeypatch.setattr(bot_loop, "build_target_leverage_from_market", fake_build_target_leverage_from_market)
    monkeypatch.setattr(bot_loop, "run_rebalance", fake_run_rebalance)
    return calls


def test_build_target_leverage_from_market_returns_empty_when_no_eligible_symbols(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(bot_loop, "get_usdt_perpetual_symbols", lambda client: ["BTCUSDT"])
    monkeypatch.setattr(bot_loop, "get_eligible_symbols", lambda client, symbols: [])

    target_leverage, selected_symbol = bot_loop.build_target_leverage_from_market(FakeClient())

    assert target_leverage == {}
    assert selected_symbol is None


def test_build_target_leverage_from_market_loads_strategy_and_returns_target(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(bot_loop, "get_usdt_perpetual_symbols", lambda client: ["BTCUSDT"])
    monkeypatch.setattr(bot_loop, "get_eligible_symbols", lambda client, symbols: ["BTCUSDT"])
    monkeypatch.setattr(bot_loop, "get_hourly_candles", lambda client, symbol, limit: [{"close": 10.0}])
    monkeypatch.setattr(
        bot_loop,
        "get_target_leverage_function",
        lambda module_path: lambda eligible_symbols, candles_by_symbol: {"BTCUSDT": 1.0},
    )

    target_leverage, selected_symbol = bot_loop.build_target_leverage_from_market(FakeClient())

    assert target_leverage == {"BTCUSDT": 1.0}
    assert selected_symbol == "BTCUSDT"


def test_run_once_initializes_rebalance_equity_when_missing(monkeypatch: MonkeyPatch) -> None:
    _patch_common_run_once_dependencies(monkeypatch, total_equity=100.0)
    state = {"rebalance_equity": None, "last_rebalance_timestamp": "existing"}

    result = bot_loop.run_once(FakeClient(), state)

    assert result["rebalance_equity"] == 100.0
    assert result["last_rebalance_status"] == "not_triggered"


def test_run_once_does_not_rebalance_below_threshold(monkeypatch: MonkeyPatch) -> None:
    calls = _patch_common_run_once_dependencies(monkeypatch, total_equity=104.0)
    state = {"rebalance_equity": 100.0, "last_rebalance_timestamp": "existing"}

    result = bot_loop.run_once(FakeClient(), state)

    assert result["last_rebalance_status"] == "not_triggered"
    assert calls["build"] == 0
    assert calls["rebalance"] == []


def test_run_once_calls_run_rebalance_when_threshold_is_reached(monkeypatch: MonkeyPatch) -> None:
    calls = _patch_common_run_once_dependencies(monkeypatch, total_equity=106.0)
    state = {"rebalance_equity": 100.0, "last_rebalance_timestamp": "existing", "rebalance_timestamps": []}

    result = bot_loop.run_once(FakeClient(), state)

    assert result["last_rebalance_status"] == "completed"
    assert calls["rebalance"] == [{"DOGEUSDT": 1.0}]


def test_run_once_calls_run_rebalance_on_start_when_enabled(monkeypatch: MonkeyPatch) -> None:
    calls = _patch_common_run_once_dependencies(monkeypatch, total_equity=100.0)
    monkeypatch.setattr(config, "RUN_REBALANCE_ON_START", 1)
    state = {"rebalance_equity": 100.0, "last_rebalance_timestamp": None, "rebalance_timestamps": []}

    bot_loop.run_once(FakeClient(), state)

    assert calls["rebalance"] == [{"DOGEUSDT": 1.0}]


def test_run_once_records_successful_rebalance_on_completed_status(monkeypatch: MonkeyPatch) -> None:
    _patch_common_run_once_dependencies(monkeypatch, total_equity=106.0)
    state = {"rebalance_equity": 100.0, "last_rebalance_timestamp": "existing", "rebalance_timestamps": []}

    result = bot_loop.run_once(FakeClient(), state)

    assert result["rebalance_equity"] == 106.0
    assert result["last_selected_symbol"] == "DOGEUSDT"
    assert result["mode"] == "normal"
    assert result["last_error"] is None


def test_run_once_stores_last_error_on_failed_status(monkeypatch: MonkeyPatch) -> None:
    _patch_common_run_once_dependencies(monkeypatch, total_equity=106.0)

    def fake_failed_rebalance(client: FakeClient, target: dict[str, float]) -> dict[str, Any]:
        return {"status": "failed", "execution_results": {"error": "boom"}}

    monkeypatch.setattr(bot_loop, "run_rebalance", fake_failed_rebalance)
    state = {"rebalance_equity": 100.0, "last_rebalance_timestamp": "existing", "rebalance_timestamps": []}

    result = bot_loop.run_once(FakeClient(), state)

    assert result["last_rebalance_status"] == "failed"
    assert "boom" in result["last_error"]
    assert result["mode"] == "error"


def test_run_once_handles_empty_target_leverage_by_calling_run_rebalance(
    monkeypatch: MonkeyPatch,
) -> None:
    calls = _patch_common_run_once_dependencies(monkeypatch, total_equity=106.0)
    monkeypatch.setattr(bot_loop, "build_target_leverage_from_market", lambda client: ({}, None))
    state = {"rebalance_equity": 100.0, "last_rebalance_timestamp": "existing", "rebalance_timestamps": []}

    result = bot_loop.run_once(FakeClient(), state)

    assert calls["rebalance"] == [{}]
    assert result["mode"] == "waiting_for_eligible_symbols"
    assert isinstance(result["next_strategy_check_timestamp"], str)


def test_run_bot_loop_handles_keyboard_interrupt_gracefully(monkeypatch: MonkeyPatch) -> None:
    logger = FakeLogger()
    monkeypatch.setattr(bot_loop, "setup_loggers", lambda: {"main": logger})
    monkeypatch.setattr(bot_loop, "_get_main_logger", lambda: logger)
    monkeypatch.setattr(bot_loop, "BybitClient", lambda: FakeClient())
    monkeypatch.setattr(bot_loop, "load_state", lambda: {})

    def raise_keyboard_interrupt(client: FakeClient, state: dict[str, Any]) -> dict[str, Any]:
        raise KeyboardInterrupt

    monkeypatch.setattr(bot_loop, "run_once", raise_keyboard_interrupt)

    bot_loop.run_bot_loop()

    assert any("stopped by user" in message for message in logger.messages)
