from __future__ import annotations

from typing import Any

import pytest

from execution.orders import (
    cancel_all_orders_for_symbol,
    get_open_orders_for_symbol,
    place_limit_order,
    place_market_order,
    qty_to_side,
)


class FakeOrderClient:
    """Small BybitClient stand-in for order helper tests."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def place_order(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("place_order", kwargs))
        return {"ok": True, "kwargs": kwargs}

    def cancel_all_orders(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("cancel_all_orders", kwargs))
        return {"ok": True, "kwargs": kwargs}

    def get_open_orders(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("get_open_orders", kwargs))
        return {"ok": True, "kwargs": kwargs}


def test_positive_qty_maps_to_buy() -> None:
    assert qty_to_side(1.0) == "Buy"


def test_negative_qty_maps_to_sell() -> None:
    assert qty_to_side(-1.0) == "Sell"


def test_zero_qty_raises_value_error() -> None:
    with pytest.raises(ValueError):
        qty_to_side(0.0)


def test_place_limit_order_calls_client_with_limit_order() -> None:
    client = FakeOrderClient()

    response = place_limit_order(client, symbol="BTCUSDT", qty=0.01, price=20_000.0)

    assert response["ok"] is True
    assert client.calls == [
        (
            "place_order",
            {
                "category": "linear",
                "symbol": "BTCUSDT",
                "side": "Buy",
                "orderType": "Limit",
                "qty": "0.01",
                "price": "20000",
                "timeInForce": "GTC",
                "reduceOnly": False,
            },
        )
    ]


def test_place_market_order_calls_client_with_market_order() -> None:
    client = FakeOrderClient()

    place_market_order(client, symbol="BTCUSDT", qty=-0.01)

    assert client.calls[-1] == (
        "place_order",
        {
            "category": "linear",
            "symbol": "BTCUSDT",
            "side": "Sell",
            "orderType": "Market",
            "qty": "0.01",
            "reduceOnly": False,
        },
    )


def test_reduce_only_is_passed_correctly() -> None:
    client = FakeOrderClient()

    place_market_order(client, symbol="BTCUSDT", qty=-0.01, reduce_only=True)

    assert client.calls[-1][1]["reduceOnly"] is True


def test_cancel_all_orders_for_symbol_calls_client() -> None:
    client = FakeOrderClient()

    cancel_all_orders_for_symbol(client, symbol="BTCUSDT")

    assert client.calls == [
        ("cancel_all_orders", {"category": "linear", "symbol": "BTCUSDT"})
    ]


def test_get_open_orders_for_symbol_calls_client() -> None:
    client = FakeOrderClient()

    get_open_orders_for_symbol(client, symbol="BTCUSDT")

    assert client.calls == [
        ("get_open_orders", {"category": "linear", "symbol": "BTCUSDT"})
    ]
