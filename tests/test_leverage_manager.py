from __future__ import annotations

from typing import Any

from pytest import MonkeyPatch

from config import config
from execution.leverage_manager import get_current_leverage, try_set_leverage_from_candidates


class FakeLeverageClient:
    """Small BybitClient stand-in for leverage tests."""

    def __init__(
        self,
        failures_before_success: int | None = 0,
        leverage_response: dict[str, Any] | None = None,
    ) -> None:
        self.failures_before_success = failures_before_success
        self.leverage_response = leverage_response or _positions_response(
            [{"symbol": "BTCUSDT"}]
        )
        self.calls: list[dict[str, Any]] = []
        self.position_calls: list[dict[str, Any]] = []

    def get_positions(self, **kwargs: Any) -> dict[str, Any]:
        self.position_calls.append(kwargs)
        return self.leverage_response

    def set_leverage(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        if self.failures_before_success is None:
            raise RuntimeError("always fails")
        if len(self.calls) <= self.failures_before_success:
            raise RuntimeError("temporary failure")
        return {"ok": True}


def test_get_current_leverage_parses_buy_and_sell_leverage() -> None:
    client = FakeLeverageClient(
        leverage_response=_positions_response(
            [{"symbol": "BTCUSDT", "buyLeverage": "50", "sellLeverage": "50"}]
        )
    )

    result = get_current_leverage(client, "BTCUSDT")

    assert result == 50.0
    assert client.position_calls == [
        {"category": "linear", "symbol": "BTCUSDT", "settle_coin": "USDT"}
    ]


def test_get_current_leverage_returns_none_if_leverage_missing() -> None:
    client = FakeLeverageClient(leverage_response=_positions_response([{"symbol": "BTCUSDT"}]))

    assert get_current_leverage(client, "BTCUSDT") is None


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


def test_current_fifty_tries_higher_only_and_keeps_current_if_higher_fails() -> None:
    client = FakeLeverageClient(
        failures_before_success=None,
        leverage_response=_positions_response(
            [{"symbol": "BTCUSDT", "buyLeverage": "50", "sellLeverage": "50"}]
        ),
    )

    result = try_set_leverage_from_candidates(client, "BTCUSDT", [100, 50, 30, 20])

    assert result == 50.0
    assert [call["buy_leverage"] for call in client.calls] == ["100"]


def test_current_thirty_tries_higher_candidates_then_keeps_current() -> None:
    client = FakeLeverageClient(
        failures_before_success=None,
        leverage_response=_positions_response(
            [{"symbol": "BTCUSDT", "buyLeverage": "30", "sellLeverage": "30"}]
        ),
    )

    result = try_set_leverage_from_candidates(client, "BTCUSDT", [100, 50, 30, 20])

    assert result == 30.0
    assert [call["buy_leverage"] for call in client.calls] == ["100", "50"]


def test_never_calls_set_leverage_with_candidate_lower_than_current() -> None:
    client = FakeLeverageClient(
        leverage_response=_positions_response(
            [{"symbol": "BTCUSDT", "buyLeverage": "50", "sellLeverage": "50"}]
        ),
    )

    result = try_set_leverage_from_candidates(client, "BTCUSDT", [30, 20])

    assert result == 50.0
    assert client.calls == []


def _positions_response(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"result": {"list": rows}}
