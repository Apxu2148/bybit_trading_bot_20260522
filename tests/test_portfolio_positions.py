from __future__ import annotations

from typing import Any

from pytest import MonkeyPatch

from bybit.client import BybitAPIRequestError
from config import config
from portfolio.positions import (
    get_current_positions,
    get_total_equity,
    parse_positions_response,
    parse_wallet_balance_response,
)


def test_parse_wallet_balance_response_parses_account_level_total_equity() -> None:
    response = {"result": {"list": [{"totalEquity": "12.34", "coin": []}]}}

    assert parse_wallet_balance_response(response) == 12.34


def test_parse_wallet_balance_response_falls_back_to_usdt_coin_equity() -> None:
    response = {
        "result": {
            "list": [
                {
                    "coin": [
                        {"coin": "BTC", "equity": "0.1", "usdValue": "10000"},
                        {"coin": "USDT", "equity": "9.87", "usdValue": "9.86"},
                    ]
                }
            ]
        }
    }

    assert parse_wallet_balance_response(response) == 9.87


def test_parse_wallet_balance_response_handles_empty_malformed_response_safely() -> None:
    assert parse_wallet_balance_response({}) == 0.0
    assert parse_wallet_balance_response({"result": {"list": [{"coin": []}]}}) == 0.0


def test_parse_positions_response_returns_positive_qty_for_long() -> None:
    response = _positions_response([{"symbol": "BTCUSDT", "side": "Buy", "size": "0.01"}])

    assert parse_positions_response(response) == {"BTCUSDT": 0.01}


def test_parse_positions_response_returns_negative_qty_for_short() -> None:
    response = _positions_response([{"symbol": "ETHUSDT", "side": "Sell", "size": "0.2"}])

    assert parse_positions_response(response) == {"ETHUSDT": -0.2}


def test_parse_positions_response_excludes_zero_size_positions() -> None:
    response = _positions_response(
        [
            {"symbol": "BTCUSDT", "side": "Buy", "size": "0"},
            {"symbol": "ETHUSDT", "side": "Sell", "size": "0.0"},
        ]
    )

    assert parse_positions_response(response) == {}


def test_parse_positions_response_handles_empty_position_list() -> None:
    assert parse_positions_response(_positions_response([])) == {}


def test_parse_positions_response_handles_malformed_rows_safely() -> None:
    response = _positions_response(
        [
            "not-a-dict",
            {"side": "Buy", "size": "1"},
            {"symbol": "BTCUSDT", "side": "Buy", "size": "bad"},
            {"symbol": "ETHUSDT", "side": "Unknown", "size": "1"},
        ]
    )

    assert parse_positions_response(response) == {}


def test_get_total_equity_adds_exchange_equity_and_reserve_balance() -> None:
    assert get_total_equity(exchange_equity=10.0, reserve_balance=2.5) == 12.5


def test_get_total_equity_uses_config_reserve_balance_if_none(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(config, "RESERVE_BALANCE_USDT", 40.0)

    assert get_total_equity(exchange_equity=10.0) == 50.0


def test_get_current_positions_uses_usdt_settle_coin_on_primary_path() -> None:
    client = FakePositionsClient(
        responses=[
            _positions_response([{"symbol": "BTCUSDT", "side": "Buy", "size": "0.01"}])
        ]
    )

    positions = get_current_positions(client)

    assert positions == {"BTCUSDT": 0.01}
    assert client.calls == [{"category": "linear", "settle_coin": "USDT"}]


def test_get_current_positions_does_not_call_fallback_if_primary_succeeds() -> None:
    client = FakePositionsClient(
        responses=[
            _positions_response([{"symbol": "BTCUSDT", "side": "Buy", "size": "0.01"}])
        ]
    )

    get_current_positions(client)

    assert len(client.calls) == 1


def test_get_current_positions_calls_fallback_only_if_primary_fails() -> None:
    client = FakePositionsClient(
        responses=[
            BybitAPIRequestError("primary failed"),
            _positions_response([{"symbol": "ETHUSDT", "side": "Sell", "size": "0.2"}]),
        ]
    )

    positions = get_current_positions(client)

    assert positions == {"ETHUSDT": -0.2}
    assert client.calls == [
        {"category": "linear", "settle_coin": "USDT"},
        {"category": "linear", "settle_coin": None},
    ]


def _positions_response(rows: list[Any]) -> dict[str, Any]:
    return {"result": {"list": rows}}


class FakePositionsClient:
    """BybitClient stand-in for get_current_positions tests."""

    def __init__(self, responses: list[dict[str, Any] | Exception]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def get_positions(
        self,
        category: str = "linear",
        symbol: str | None = None,
        settle_coin: str | None = "USDT",
    ) -> dict[str, Any]:
        call: dict[str, Any] = {"category": category, "settle_coin": settle_coin}
        if symbol is not None:
            call["symbol"] = symbol
        self.calls.append(call)

        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response
