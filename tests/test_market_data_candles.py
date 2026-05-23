from __future__ import annotations

from typing import Any

from pytest import MonkeyPatch

from market_data import candles as candles_module
from market_data.candles import (
    filter_unfinished_last_candle,
    get_candles,
    get_last_close,
    should_include_last_candle,
)


class FakeKlineClient:
    """BybitClient stand-in for candle tests."""

    def __init__(self, rows: list[Any]) -> None:
        self.rows = rows
        self.calls: list[dict[str, Any]] = []

    def get_kline(
        self,
        category: str,
        symbol: str,
        interval: str,
        limit: int,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "category": category,
                "symbol": symbol,
                "interval": interval,
                "limit": limit,
            }
        )
        return {"result": {"list": self.rows}}


def test_parses_bybit_kline_response_into_normalized_candle_dicts() -> None:
    client = FakeKlineClient(
        [["1000", "1.0", "2.0", "0.5", "1.5", "10", "15"]]
    )

    candles = get_candles(client=client, symbol="BTCUSDT", interval="1", limit=1)

    assert candles == [
        {
            "start_time_ms": 1000,
            "open": 1.0,
            "high": 2.0,
            "low": 0.5,
            "close": 1.5,
            "volume": 10.0,
            "turnover": 15.0,
        }
    ]
    assert client.calls == [{"category": "linear", "symbol": "BTCUSDT", "interval": "1", "limit": 1}]


def test_sorts_candles_ascending_by_start_time_ms() -> None:
    client = FakeKlineClient(
        [
            ["3000", "1", "1", "1", "3", "10", "30"],
            ["1000", "1", "1", "1", "1", "10", "10"],
            ["2000", "1", "1", "1", "2", "10", "20"],
        ]
    )

    candles = get_candles(client=client, symbol="BTCUSDT", interval="1", limit=3)

    assert [candle["start_time_ms"] for candle in candles] == [1000, 2000, 3000]


def test_should_include_last_candle_uses_more_than_half_period_rule() -> None:
    start_ms = 1_000_000

    assert should_include_last_candle(start_ms, 60, now_ms=start_ms + 29_999) is False
    assert should_include_last_candle(start_ms, 60, now_ms=start_ms + 30_000) is False
    assert should_include_last_candle(start_ms, 60, now_ms=start_ms + 30_001) is True


def test_filter_unfinished_last_candle_removes_latest_when_half_or_less_elapsed(
    monkeypatch: MonkeyPatch,
) -> None:
    now_ms = 130_000
    monkeypatch.setattr(candles_module.time, "time", lambda: now_ms / 1000)
    candles = [
        {"start_time_ms": 70_000, "close": 1.0},
        {"start_time_ms": 100_000, "close": 2.0},
    ]

    filtered = filter_unfinished_last_candle(candles, interval_seconds=60)

    assert filtered == [{"start_time_ms": 70_000, "close": 1.0}]


def test_filter_unfinished_last_candle_keeps_latest_when_more_than_half_elapsed(
    monkeypatch: MonkeyPatch,
) -> None:
    now_ms = 130_001
    monkeypatch.setattr(candles_module.time, "time", lambda: now_ms / 1000)
    candles = [
        {"start_time_ms": 70_000, "close": 1.0},
        {"start_time_ms": 100_000, "close": 2.0},
    ]

    filtered = filter_unfinished_last_candle(candles, interval_seconds=60)

    assert filtered == candles


def test_get_last_close_returns_final_close() -> None:
    candles = [
        {"start_time_ms": 1, "close": 10.0},
        {"start_time_ms": 2, "close": "11.5"},
    ]

    assert get_last_close(candles) == 11.5


def test_handles_empty_and_malformed_candle_data_safely() -> None:
    malformed_client = FakeKlineClient(
        [
            ["bad-start", "1", "2", "0.5", "1.5", "10", "15"],
            ["1000", "bad-open", "2", "0.5", "1.5", "10", "15"],
            {"not": "a bybit kline row"},
        ]
    )
    empty_client = FakeKlineClient([])

    assert get_candles(client=malformed_client, symbol="BTCUSDT", interval="1", limit=3) == []
    assert get_candles(client=empty_client, symbol="BTCUSDT", interval="1", limit=3) == []
    assert get_last_close([]) is None
