from __future__ import annotations

from typing import Any

from pytest import MonkeyPatch

from config import config
from execution.cleanup import cleanup_small_positions


class FakeCleanupClient:
    """Small BybitClient stand-in for cleanup tests."""

    def __init__(self, outcomes: list[bool] | None = None) -> None:
        self.outcomes = list(outcomes or [])
        self.calls: list[dict[str, Any]] = []

    def place_order(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        should_succeed = True if not self.outcomes else self.outcomes.pop(0)
        if not should_succeed:
            raise RuntimeError("order rejected")
        return {"ok": True}


def _patch_cleanup_config(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(config, "MIN_POSITION_NOTIONAL_USDT", 5.0)
    monkeypatch.setattr(config, "SMALL_POSITION_CLEANUP_MAX_MARKET_ATTEMPTS", 2)
    monkeypatch.setattr(config, "SMALL_POSITION_CLEANUP_MAX_REDUCE_ONLY_ATTEMPTS", 2)


def test_skips_positions_above_min_notional(monkeypatch: MonkeyPatch) -> None:
    _patch_cleanup_config(monkeypatch)
    client = FakeCleanupClient()

    result = cleanup_small_positions(
        client=client,
        current_positions={"BTCUSDT": 0.01},
        last_close_prices={"BTCUSDT": 20_000.0},
    )

    assert result == {"closed": [], "failed": [], "skipped": ["BTCUSDT"]}
    assert client.calls == []


def test_tries_close_for_small_positions(monkeypatch: MonkeyPatch) -> None:
    _patch_cleanup_config(monkeypatch)
    client = FakeCleanupClient()

    result = cleanup_small_positions(
        client=client,
        current_positions={"DOGEUSDT": 10.0},
        last_close_prices={"DOGEUSDT": 0.1},
    )

    assert result == {"closed": ["DOGEUSDT"], "failed": [], "skipped": []}
    assert client.calls[0]["symbol"] == "DOGEUSDT"
    assert client.calls[0]["side"] == "Sell"
    assert client.calls[0]["reduceOnly"] is False


def test_retries_normal_market_attempts(monkeypatch: MonkeyPatch) -> None:
    _patch_cleanup_config(monkeypatch)
    monkeypatch.setattr(config, "SMALL_POSITION_CLEANUP_MAX_MARKET_ATTEMPTS", 2)
    monkeypatch.setattr(config, "SMALL_POSITION_CLEANUP_MAX_REDUCE_ONLY_ATTEMPTS", 0)
    client = FakeCleanupClient(outcomes=[False, True])

    result = cleanup_small_positions(
        client=client,
        current_positions={"DOGEUSDT": 10.0},
        last_close_prices={"DOGEUSDT": 0.1},
    )

    assert result["closed"] == ["DOGEUSDT"]
    assert len(client.calls) == 2
    assert all(call["reduceOnly"] is False for call in client.calls)


def test_retries_reduce_only_after_normal_failures(monkeypatch: MonkeyPatch) -> None:
    _patch_cleanup_config(monkeypatch)
    monkeypatch.setattr(config, "SMALL_POSITION_CLEANUP_MAX_MARKET_ATTEMPTS", 1)
    monkeypatch.setattr(config, "SMALL_POSITION_CLEANUP_MAX_REDUCE_ONLY_ATTEMPTS", 1)
    client = FakeCleanupClient(outcomes=[False, True])

    result = cleanup_small_positions(
        client=client,
        current_positions={"DOGEUSDT": -10.0},
        last_close_prices={"DOGEUSDT": 0.1},
    )

    assert result["closed"] == ["DOGEUSDT"]
    assert [call["reduceOnly"] for call in client.calls] == [False, True]
    assert [call["side"] for call in client.calls] == ["Buy", "Buy"]


def test_returns_failed_if_all_attempts_fail(monkeypatch: MonkeyPatch) -> None:
    _patch_cleanup_config(monkeypatch)
    monkeypatch.setattr(config, "SMALL_POSITION_CLEANUP_MAX_MARKET_ATTEMPTS", 1)
    monkeypatch.setattr(config, "SMALL_POSITION_CLEANUP_MAX_REDUCE_ONLY_ATTEMPTS", 1)
    client = FakeCleanupClient(outcomes=[False, False])

    result = cleanup_small_positions(
        client=client,
        current_positions={"DOGEUSDT": 10.0},
        last_close_prices={"DOGEUSDT": 0.1},
    )

    assert result == {"closed": [], "failed": ["DOGEUSDT"], "skipped": []}
    assert len(client.calls) == 2
