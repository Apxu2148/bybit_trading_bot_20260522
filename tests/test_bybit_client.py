from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest
from pytest import MonkeyPatch

from config import config
from bybit import client as client_module
from bybit.client import (
    BybitAPIRequestError,
    BybitClient,
    MissingBybitCredentialsError,
)


class FakeHTTP:
    """Small pybit HTTP stand-in used to keep tests offline."""

    last_instance: "FakeHTTP | None" = None

    def __init__(self, **kwargs: Any) -> None:
        self.init_kwargs = kwargs
        self.calls: list[tuple[str, dict[str, Any]]] = []
        FakeHTTP.last_instance = self

    def get_instruments_info(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("get_instruments_info", kwargs))
        return {"ok": True, "method": "get_instruments_info", "kwargs": kwargs}

    def get_kline(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("get_kline", kwargs))
        return {"ok": True, "method": "get_kline", "kwargs": kwargs}

    def get_tickers(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("get_tickers", kwargs))
        return {"ok": True, "method": "get_tickers", "kwargs": kwargs}

    def get_wallet_balance(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("get_wallet_balance", kwargs))
        return {"ok": True, "method": "get_wallet_balance", "kwargs": kwargs}

    def get_positions(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("get_positions", kwargs))
        return {"ok": True, "method": "get_positions", "kwargs": kwargs}

    def place_order(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("place_order", kwargs))
        return {"ok": True, "method": "place_order", "kwargs": kwargs}

    def cancel_all_orders(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("cancel_all_orders", kwargs))
        return {"ok": True, "method": "cancel_all_orders", "kwargs": kwargs}

    def get_open_orders(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("get_open_orders", kwargs))
        return {"ok": True, "method": "get_open_orders", "kwargs": kwargs}

    def set_leverage(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("set_leverage", kwargs))
        return {"ok": True, "method": "set_leverage", "kwargs": kwargs}

    def set_margin_mode(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("set_margin_mode", kwargs))
        return {"ok": True, "method": "set_margin_mode", "kwargs": kwargs}

    def switch_margin_mode(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("switch_margin_mode", kwargs))
        return {"ok": True, "method": "switch_margin_mode", "kwargs": kwargs}


@pytest.fixture
def client_test_env(tmp_path: Path, monkeypatch: MonkeyPatch) -> Path:
    """Patch the client so tests never create live pybit sessions."""
    FakeHTTP.last_instance = None
    monkeypatch.setattr(client_module, "PybitHTTP", FakeHTTP)
    monkeypatch.setattr(client_module, "API_KEYS_FILE_PATH", tmp_path / "api_keys.py")
    monkeypatch.setattr(config, "LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setattr(config, "API_MAX_RETRIES", 2)
    monkeypatch.setattr(config, "API_RETRY_DELAY_SECONDS", 0.0)
    monkeypatch.setattr(config, "MAX_API_REQUESTS_PER_SECOND", 1_000_000)
    return tmp_path


def test_import_bybit_client() -> None:
    from bybit.client import BybitClient as ImportedBybitClient

    assert ImportedBybitClient is BybitClient


def test_missing_credentials_private_call_raises(client_test_env: Path) -> None:
    client = BybitClient()

    assert client.has_credentials() is False
    with pytest.raises(MissingBybitCredentialsError):
        client.get_wallet_balance()


def test_existing_credentials_are_loaded_without_printing_values(
    client_test_env: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    credentials_path = client_test_env / "api_keys.py"
    credentials_path.write_text('API_KEY = "test_key"\nAPI_SECRET = "test_secret"\n', encoding="utf-8")

    client = BybitClient()
    captured = capsys.readouterr()

    assert client.has_credentials() is True
    assert client.api_key == "test_key"
    assert client.api_secret == "test_secret"
    assert "test_key" not in captured.out
    assert "test_secret" not in captured.out


def test_public_wrapper_call_uses_underlying_session(client_test_env: Path) -> None:
    client = BybitClient()

    result = client.get_instruments_info()

    assert result["kwargs"] == {"category": "linear"}
    assert FakeHTTP.last_instance is not None
    assert FakeHTTP.last_instance.calls[-1] == ("get_instruments_info", {"category": "linear"})


def test_get_positions_passes_usdt_settle_coin_by_default(client_test_env: Path) -> None:
    credentials_path = client_test_env / "api_keys.py"
    credentials_path.write_text('API_KEY = "test_key"\nAPI_SECRET = "test_secret"\n', encoding="utf-8")
    client = BybitClient()

    result = client.get_positions()

    assert result["method"] == "get_positions"
    assert FakeHTTP.last_instance is not None
    assert FakeHTTP.last_instance.calls[-1] == (
        "get_positions",
        {"category": "linear", "settleCoin": "USDT"},
    )


def test_get_positions_can_omit_settle_coin(client_test_env: Path) -> None:
    credentials_path = client_test_env / "api_keys.py"
    credentials_path.write_text('API_KEY = "test_key"\nAPI_SECRET = "test_secret"\n', encoding="utf-8")
    client = BybitClient()

    result = client.get_positions(category="linear", symbol=None, settle_coin=None)

    assert result["method"] == "get_positions"
    assert FakeHTTP.last_instance is not None
    assert FakeHTTP.last_instance.calls[-1] == ("get_positions", {"category": "linear"})


def test_retry_logic_success(client_test_env: Path) -> None:
    client = BybitClient()
    calls = {"count": 0}

    def flaky_call(**kwargs: Any) -> dict[str, Any]:
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("temporary")
        return {"ok": True, "kwargs": kwargs}

    result = client._make_public_call(flaky_call, category="linear")

    assert result == {"ok": True, "kwargs": {"category": "linear"}}
    assert calls["count"] == 2


def test_retry_logic_failure(client_test_env: Path) -> None:
    client = BybitClient()

    def failing_call(**kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("permanent")

    with pytest.raises(BybitAPIRequestError):
        client._make_public_call(failing_call)


def test_semaphore_uses_configured_limit(client_test_env: Path) -> None:
    client = BybitClient()

    assert client.semaphore is not None
    assert client.semaphore._value == config.API_SEMAPHORE_LIMIT


def test_place_order_uses_mocked_session_only(client_test_env: Path) -> None:
    credentials_path = client_test_env / "api_keys.py"
    credentials_path.write_text('API_KEY = "test_key"\nAPI_SECRET = "test_secret"\n', encoding="utf-8")
    client = BybitClient()

    result = client.place_order(category="linear", symbol="BTCUSDT", side="Buy")

    assert result["method"] == "place_order"
    assert FakeHTTP.last_instance is not None
    assert FakeHTTP.last_instance.calls[-1] == (
        "place_order",
        {"category": "linear", "symbol": "BTCUSDT", "side": "Buy"},
    )
