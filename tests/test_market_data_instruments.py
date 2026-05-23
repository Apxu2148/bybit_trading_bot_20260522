from __future__ import annotations

from typing import Any

from market_data.instruments import (
    get_instrument_info,
    get_instruments_info,
    get_usdt_perpetual_symbols,
)


class FakeInstrumentsClient:
    """BybitClient stand-in for instrument tests."""

    def __init__(
        self,
        rows: list[Any] | None = None,
        responses: list[dict[str, Any]] | None = None,
    ) -> None:
        self.responses = responses or [{"result": {"list": rows or []}}]
        self.calls: list[dict[str, Any]] = []

    def get_instruments_info(self, category: str, cursor: str | None = None) -> dict[str, Any]:
        call = {"category": category}
        if cursor is not None:
            call["cursor"] = cursor
        self.calls.append(call)
        index = min(len(self.calls) - 1, len(self.responses) - 1)
        return self.responses[index]


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


def test_get_instruments_info_loads_multiple_pages_when_cursor_exists() -> None:
    client = FakeInstrumentsClient(
        responses=[
            {
                "result": {
                    "list": [
                        {
                            "symbol": "BTCUSDT",
                            "quoteCoin": "USDT",
                            "settleCoin": "USDT",
                            "contractType": "LinearPerpetual",
                            "status": "Trading",
                        }
                    ],
                    "nextPageCursor": "page-2",
                }
            },
            {
                "result": {
                    "list": [
                        {
                            "symbol": "XRPUSDT",
                            "quoteCoin": "USDT",
                            "settleCoin": "USDT",
                            "contractType": "LinearPerpetual",
                            "status": "Trading",
                        }
                    ],
                    "nextPageCursor": "",
                }
            },
        ]
    )

    instruments = get_instruments_info(client)

    assert list(instruments) == ["BTCUSDT", "XRPUSDT"]
    assert client.calls == [
        {"category": "linear"},
        {"category": "linear", "cursor": "page-2"},
    ]


def test_pagination_stops_when_next_page_cursor_is_empty() -> None:
    client = FakeInstrumentsClient(
        responses=[
            {
                "result": {
                    "list": [
                        {
                            "symbol": "BTCUSDT",
                            "quoteCoin": "USDT",
                            "settleCoin": "USDT",
                            "contractType": "LinearPerpetual",
                            "status": "Trading",
                        }
                    ],
                    "nextPageCursor": "",
                }
            },
            {
                "result": {
                    "list": [
                        {
                            "symbol": "SHOULDNOTLOADUSDT",
                            "quoteCoin": "USDT",
                            "settleCoin": "USDT",
                            "contractType": "LinearPerpetual",
                            "status": "Trading",
                        }
                    ]
                }
            },
        ]
    )

    instruments = get_instruments_info(client)

    assert list(instruments) == ["BTCUSDT"]
    assert client.calls == [{"category": "linear"}]


def test_pagination_stops_if_cursor_repeats() -> None:
    client = FakeInstrumentsClient(
        responses=[
            {
                "result": {
                    "list": [
                        {
                            "symbol": "BTCUSDT",
                            "quoteCoin": "USDT",
                            "settleCoin": "USDT",
                            "contractType": "LinearPerpetual",
                            "status": "Trading",
                        }
                    ],
                    "nextPageCursor": "repeat",
                }
            },
            {
                "result": {
                    "list": [
                        {
                            "symbol": "SOLUSDT",
                            "quoteCoin": "USDT",
                            "settleCoin": "USDT",
                            "contractType": "LinearPerpetual",
                            "status": "Trading",
                        }
                    ],
                    "nextPageCursor": "repeat",
                }
            },
            {
                "result": {
                    "list": [
                        {
                            "symbol": "SHOULDNOTLOADUSDT",
                            "quoteCoin": "USDT",
                            "settleCoin": "USDT",
                            "contractType": "LinearPerpetual",
                            "status": "Trading",
                        }
                    ]
                }
            },
        ]
    )

    instruments = get_instruments_info(client)

    assert list(instruments) == ["BTCUSDT", "SOLUSDT"]
    assert client.calls == [
        {"category": "linear"},
        {"category": "linear", "cursor": "repeat"},
    ]


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
