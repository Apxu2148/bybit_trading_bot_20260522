from __future__ import annotations

from typing import Any

from market_data.instruments import (
    get_instrument_info,
    get_instruments_info,
    get_usdt_perpetual_symbols,
)


class FakeInstrumentsClient:
    """BybitClient stand-in for instrument tests."""

    def __init__(self, rows: list[Any]) -> None:
        self.rows = rows
        self.calls: list[dict[str, Any]] = []

    def get_instruments_info(self, category: str) -> dict[str, Any]:
        self.calls.append({"category": category})
        return {"result": {"list": self.rows}}


def test_parses_active_usdt_linear_perpetual_symbols() -> None:
    client = FakeInstrumentsClient(
        [
            {
                "symbol": "BTCUSDT",
                "quoteCoin": "USDT",
                "settleCoin": "USDT",
                "contractType": "LinearPerpetual",
                "status": "Trading",
            },
            {
                "symbol": "SOLUSDT",
                "quoteCoin": "USDT",
                "settleCoin": "USDT",
                "contractType": "LinearPerpetual",
                "status": "Trading",
            },
        ]
    )

    assert get_usdt_perpetual_symbols(client) == ["BTCUSDT", "SOLUSDT"]
    assert client.calls == [{"category": "linear"}]


def test_excludes_non_usdt_symbols() -> None:
    client = FakeInstrumentsClient(
        [
            {
                "symbol": "BTCUSD",
                "quoteCoin": "USD",
                "settleCoin": "BTC",
                "contractType": "LinearPerpetual",
                "status": "Trading",
            },
            {
                "symbol": "ETHUSDT",
                "quoteCoin": "USDT",
                "settleCoin": "USDT",
                "contractType": "LinearPerpetual",
                "status": "Trading",
            },
        ]
    )

    assert get_usdt_perpetual_symbols(client) == ["ETHUSDT"]


def test_excludes_inactive_non_trading_symbols() -> None:
    client = FakeInstrumentsClient(
        [
            {
                "symbol": "BTCUSDT",
                "quoteCoin": "USDT",
                "settleCoin": "USDT",
                "contractType": "LinearPerpetual",
                "status": "Trading",
            },
            {
                "symbol": "SOLUSDT",
                "quoteCoin": "USDT",
                "settleCoin": "USDT",
                "contractType": "LinearPerpetual",
                "status": "Settling",
            },
        ]
    )

    assert get_usdt_perpetual_symbols(client) == ["BTCUSDT"]


def test_skips_malformed_instruments_safely() -> None:
    client = FakeInstrumentsClient(
        [
            "not-a-dict",
            {"quoteCoin": "USDT", "contractType": "LinearPerpetual", "status": "Trading"},
            {"symbol": "BROKENUSDT", "quoteCoin": "USDT", "status": "Trading"},
            {
                "symbol": "BTCUSDT",
                "quoteCoin": "USDT",
                "settleCoin": "USDT",
                "contractType": "LinearPerpetual",
                "status": "Trading",
            },
        ]
    )

    instruments = get_instruments_info(client)

    assert list(instruments) == ["BTCUSDT"]
    assert get_instrument_info(client, "btcusdt") == instruments["BTCUSDT"]
