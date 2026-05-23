from __future__ import annotations

from typing import Any

from pytest import MonkeyPatch

from config import config
from execution.leverage_manager import try_set_leverage_from_candidates


class FakeLeverageClient:
    """Small BybitClient stand-in for leverage tests."""

    def __init__(self, failures_before_success: int | None = 0) -> None:
        self.failures_before_success = failures_before_success
        self.calls: list[dict[str, Any]] = []

    def set_leverage(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        if self.failures_before_success is None:
            raise RuntimeError("always fails")
        if len(self.calls) <= self.failures_before_success:
            raise RuntimeError("temporary failure")
        return {"ok": True}


def test_first_candidate_succeeds() -> None:
    client = FakeLeverageClient()

    result = try_set_leverage_from_candidates(client, "BTCUSDT", [10, 5])

    assert result == 10
    assert client.calls == [
        {
            "symbol": "BTCUSDT",
            "buy_leverage": "10",
            "sell_leverage": "10",
            "category": "linear",
        }
    ]


def test_first_fails_second_succeeds() -> None:
    client = FakeLeverageClient(failures_before_success=1)

    result = try_set_leverage_from_candidates(client, "BTCUSDT", [100, 50])

    assert result == 50
    assert [call["buy_leverage"] for call in client.calls] == ["100", "50"]


def test_all_fail_returns_none() -> None:
    client = FakeLeverageClient(failures_before_success=None)

    result = try_set_leverage_from_candidates(client, "BTCUSDT", [100, 50])

    assert result is None
    assert [call["buy_leverage"] for call in client.calls] == ["100", "50"]


def test_default_config_leverage_candidates_are_used(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(config, "LEVERAGE_CANDIDATES", [7, 3])
    client = FakeLeverageClient()

    result = try_set_leverage_from_candidates(client, "ETHUSDT")

    assert result == 7
    assert client.calls[0]["buy_leverage"] == "7"
