"""Bybit REST client wrapper foundation.

This module is the only low-level place where future project modules should
interact with Bybit REST API. Market data, portfolio, execution, and risk code
must call methods on BybitClient instead of importing pybit directly. Keeping
the exchange-specific layer here makes it easier to test, replace, and audit.

Stage 3 intentionally provides thin wrappers only. It does not implement
trading strategy logic, rebalance execution logic, or any script that places
real orders.

Security note:
    Never log API keys, API secrets, signatures, or full request headers. This
    client logs only credential presence, request method names, and sanitized
    error classes. Future code should keep this same rule at every call site.
"""

from __future__ import annotations

import asyncio
import importlib.util
import logging
import threading
import time
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

try:
    from pybit.exceptions import FailedRequestError, InvalidRequestError, UnauthorizedExceptionError
    from pybit.unified_trading import HTTP as PybitHTTP
except ImportError as exc:  # pragma: no cover - exercised only if dependency is missing.
    raise RuntimeError("pybit is required for bybit.client. Install requirements.txt in .venv.") from exc

from config import config
from logging_setup.logger import get_loggers

API_KEYS_FILE_PATH = Path(__file__).resolve().parents[1] / "secrets" / "api_keys.py"

PybitRequestException = (
    FailedRequestError,
    InvalidRequestError,
    UnauthorizedExceptionError,
    TimeoutError,
    ConnectionError,
)


class BybitClientError(Exception):
    """Base exception for Bybit client wrapper errors."""


class MissingBybitCredentialsError(BybitClientError):
    """Raised when a private Bybit REST method is called without credentials."""


class BybitAPIRequestError(BybitClientError):
    """Raised when a Bybit REST request fails after configured retries."""


class BybitClient:
    """Thin, reusable wrapper around pybit unified_trading.HTTP."""

    def __init__(self) -> None:
        """Initialize a mainnet REST session and Stage 3 request helpers."""
        self.loggers: dict[str, logging.Logger] = get_loggers()
        self.api_key, self.api_secret = self._load_credentials()

        # The semaphore is present now so future async code has a shared place
        # to coordinate request bursts. Stage 3 methods remain synchronous
        # because pybit's HTTP client is synchronous.
        self.semaphore = asyncio.Semaphore(config.API_SEMAPHORE_LIMIT)

        # A simple synchronous throttle is enough for Stage 3. More advanced
        # endpoint-specific rate limiting can be added later without changing
        # module callers.
        self._rate_limit_lock = threading.Lock()
        self._last_request_timestamp = 0.0
        self._max_requests_per_second = float(config.MAX_API_REQUESTS_PER_SECOND)

        self.session: Any = self._create_session()
        credential_status = "found" if self.has_credentials() else "missing"
        self.loggers["main"].info("Bybit REST client initialized; credentials %s.", credential_status)

    def has_credentials(self) -> bool:
        """Return True when both API key and API secret are available."""
        return bool(self.api_key and self.api_secret)

    def _get_session(self) -> Any:
        """Return the underlying pybit HTTP session."""
        return self.session

    def _make_public_call(self, callable_obj: Callable[..., Any], **kwargs: Any) -> Any:
        """Run a public REST call through retry handling.

        Public calls are allowed without credentials when Bybit supports the
        endpoint anonymously.
        """
        return self._call_with_retries(callable_obj, **kwargs)

    def _make_private_call(self, callable_obj: Callable[..., Any], **kwargs: Any) -> Any:
        """Run a private REST call after verifying credentials exist."""
        if not self.has_credentials():
            raise MissingBybitCredentialsError(
                "Bybit API credentials are missing. Copy secrets/api_keys.example.py "
                "to secrets/api_keys.py and fill API_KEY and API_SECRET."
            )
        return self._call_with_retries(callable_obj, **kwargs)

    def get_instruments_info(
        self,
        category: str = "linear",
        cursor: str | None = None,
        limit: int | None = None,
    ) -> Any:
        """Get Bybit instrument metadata for a category."""
        params: dict[str, Any] = {"category": category}
        if cursor is not None:
            params["cursor"] = cursor
        if limit is not None:
            params["limit"] = limit
        return self._make_public_call(self._get_session().get_instruments_info, **params)

    def get_kline(
        self,
        symbol: str,
        interval: str,
        limit: int,
        category: str = "linear",
    ) -> Any:
        """Get kline data for a symbol and interval."""
        return self._make_public_call(
            self._get_session().get_kline,
            category=category,
            symbol=symbol,
            interval=interval,
            limit=limit,
        )

    def get_tickers(self, category: str = "linear", symbol: str | None = None) -> Any:
        """Get ticker data for all symbols in a category or one symbol."""
        params: dict[str, Any] = {"category": category}
        if symbol is not None:
            params["symbol"] = symbol
        return self._make_public_call(self._get_session().get_tickers, **params)

    def get_wallet_balance(self, account_type: str = "UNIFIED") -> Any:
        """Get wallet balance for a Bybit account type."""
        return self._make_private_call(self._get_session().get_wallet_balance, accountType=account_type)

    def get_positions(
        self,
        category: str = "linear",
        symbol: str | None = None,
        settle_coin: str | None = "USDT",
    ) -> Any:
        """Get current positions for all symbols in a category or one symbol."""
        params: dict[str, Any] = {"category": category}
        if symbol is not None:
            params["symbol"] = symbol
        if settle_coin is not None:
            params["settleCoin"] = settle_coin
        return self._make_private_call(self._get_session().get_positions, **params)

    def place_order(self, **kwargs: Any) -> Any:
        """Place an order through Bybit.

        This method is a thin wrapper for future stages. Stage 3 tests must not
        call it against a real session.
        """
        return self._make_private_call(self._get_session().place_order, **kwargs)

    def cancel_all_orders(self, category: str = "linear", symbol: str | None = None) -> Any:
        """Cancel open orders for a category and optional symbol."""
        params: dict[str, Any] = {"category": category}
        if symbol is not None:
            params["symbol"] = symbol
        return self._make_private_call(self._get_session().cancel_all_orders, **params)

    def get_open_orders(self, category: str = "linear", symbol: str | None = None) -> Any:
        """Get open orders for a category and optional symbol."""
        params: dict[str, Any] = {"category": category}
        if symbol is not None:
            params["symbol"] = symbol
        return self._make_private_call(self._get_session().get_open_orders, **params)

    def set_leverage(
        self,
        symbol: str,
        buy_leverage: str,
        sell_leverage: str,
        category: str = "linear",
    ) -> Any:
        """Set buy and sell leverage for a symbol."""
        return self._make_private_call(
            self._get_session().set_leverage,
            category=category,
            symbol=symbol,
            buyLeverage=buy_leverage,
            sellLeverage=sell_leverage,
        )

    def set_margin_mode(self, **kwargs: Any) -> Any:
        """Set margin mode through pybit's supported method.

        pybit exposes this endpoint as a kwargs-based method. Future stages
        should define the project-level parameters before this method is used in
        execution flows.
        """
        return self._make_private_call(self._get_session().set_margin_mode, **kwargs)

    def switch_margin_mode(self, **kwargs: Any) -> Any:
        """Switch margin mode through pybit's supported method."""
        return self._make_private_call(self._get_session().switch_margin_mode, **kwargs)

    def _create_session(self) -> Any:
        """Create a pybit HTTP session configured for Bybit mainnet."""
        session_kwargs: dict[str, Any] = {"testnet": False}
        if self.has_credentials():
            session_kwargs["api_key"] = self.api_key
            session_kwargs["api_secret"] = self.api_secret
        return PybitHTTP(**session_kwargs)

    def _load_credentials(self) -> tuple[str | None, str | None]:
        """Load API credentials from secrets/api_keys.py if the file exists."""
        if not API_KEYS_FILE_PATH.exists():
            self.loggers["main"].info("Bybit credentials file is missing; public endpoints remain available.")
            return None, None

        module = _load_module_from_path(API_KEYS_FILE_PATH)
        api_key = getattr(module, "API_KEY", "")
        api_secret = getattr(module, "API_SECRET", "")
        if isinstance(api_key, str) and isinstance(api_secret, str) and api_key and api_secret:
            self.loggers["main"].info("Bybit credentials file loaded; credentials are present.")
            return api_key, api_secret

        self.loggers["main"].info("Bybit credentials file loaded; credentials are empty.")
        return None, None

    def _call_with_retries(self, callable_obj: Callable[..., Any], **kwargs: Any) -> Any:
        """Call a pybit method with simple retry handling and sanitized logs."""
        attempts = max(int(config.API_MAX_RETRIES), 1)
        delay_seconds = max(float(config.API_RETRY_DELAY_SECONDS), 0.0)
        call_name = _callable_name(callable_obj)
        last_error: Exception | None = None

        for attempt in range(1, attempts + 1):
            try:
                self._throttle_sync()
                return callable_obj(**kwargs)
            except PybitRequestException as exc:
                last_error = exc
                self._handle_request_exception(exc, call_name, attempt, attempts, delay_seconds)
            except Exception as exc:
                last_error = exc
                self._handle_request_exception(exc, call_name, attempt, attempts, delay_seconds)

        raise BybitAPIRequestError(f"Bybit REST request {call_name} failed: {last_error}") from last_error

    def _handle_request_exception(
        self,
        exc: Exception,
        call_name: str,
        attempt: int,
        attempts: int,
        delay_seconds: float,
    ) -> None:
        """Log sanitized retry information and raise after final failure."""
        if attempt >= attempts:
            self.loggers["main"].error(
                "Bybit REST request %s failed after %s attempt(s); error_type=%s.",
                call_name,
                attempts,
                exc.__class__.__name__,
            )
            raise BybitAPIRequestError(
                f"Bybit REST request {call_name} failed after {attempts} attempt(s)."
            ) from exc

        self.loggers["main"].warning(
            "Bybit REST request %s failed on attempt %s/%s; error_type=%s. Retrying.",
            call_name,
            attempt,
            attempts,
            exc.__class__.__name__,
        )
        if delay_seconds:
            time.sleep(delay_seconds)

    def _throttle_sync(self) -> None:
        """Apply a simple process-local synchronous request throttle."""
        if self._max_requests_per_second <= 0:
            return
        min_interval = 1.0 / self._max_requests_per_second
        with self._rate_limit_lock:
            now = time.monotonic()
            wait_seconds = self._last_request_timestamp + min_interval - now
            if wait_seconds > 0:
                time.sleep(wait_seconds)
            self._last_request_timestamp = time.monotonic()


def _load_module_from_path(path: Path) -> ModuleType:
    """Load a Python module from a file path without logging its contents."""
    spec = importlib.util.spec_from_file_location("local_bybit_api_keys", path)
    if spec is None or spec.loader is None:
        raise MissingBybitCredentialsError(f"Could not load Bybit credentials module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _callable_name(callable_obj: Callable[..., Any]) -> str:
    """Return a stable, non-secret name for a callable used in logs."""
    return getattr(callable_obj, "__name__", callable_obj.__class__.__name__)
