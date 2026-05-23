"""Instrument discovery for Bybit USDT perpetual futures."""

from __future__ import annotations

import logging
from typing import Any

from bybit.client import BybitClient
from logging_setup.logger import get_loggers


def get_usdt_perpetual_symbols(client: BybitClient) -> list[str]:
    """Return active Bybit USDT perpetual symbols from the linear category."""
    return list(get_instruments_info(client).keys())


def get_instruments_info(client: BybitClient) -> dict[str, dict[str, Any]]:
    """Return active USDT perpetual instrument metadata keyed by symbol.

    Bybit V5 returns instrument rows under ``response["result"]["list"]``.
    Each row is expected to include a symbol, quote or settle coin, contract
    type, and trading status. Fields can change or be missing, so malformed or
    unsupported rows are skipped instead of crashing universe discovery.
    """
    logger = _get_filtering_logger()
    raw_instruments = _load_all_instrument_pages(client)
    instruments: dict[str, dict[str, Any]] = {}

    for raw_instrument in raw_instruments:
        if not isinstance(raw_instrument, dict):
            logger.warning("Skipping malformed instrument row; row_type=%s.", type(raw_instrument).__name__)
            continue

        symbol = raw_instrument.get("symbol")
        if not isinstance(symbol, str) or not symbol:
            logger.warning("Skipping malformed instrument with missing symbol.")
            continue

        if not _has_required_metadata(raw_instrument, symbol):
            continue
        if not _is_usdt_contract(raw_instrument):
            continue
        if not _is_perpetual_contract(raw_instrument):
            continue
        if not _is_active_instrument(raw_instrument):
            continue

        instruments[symbol] = dict(raw_instrument)

    logger.info("Total active USDT perpetual instruments after filtering: %s.", len(instruments))
    return instruments


def get_instrument_info(
    client: BybitClient,
    symbol: str,
) -> dict[str, Any] | None:
    """Return metadata for one active USDT perpetual symbol, if available."""
    normalized_symbol = symbol.upper()
    return get_instruments_info(client).get(normalized_symbol)


def _load_all_instrument_pages(client: BybitClient) -> list[Any]:
    """Load all Bybit instrument pages using nextPageCursor pagination."""
    logger = _get_filtering_logger()
    all_instruments: list[Any] = []
    seen_cursors: set[str] = set()
    cursor: str | None = None
    page_number = 1

    while True:
        response = client.get_instruments_info(category="linear", cursor=cursor)
        page_instruments = _extract_result_list(response)
        all_instruments.extend(page_instruments)

        next_cursor = _extract_next_page_cursor(response)
        logger.info(
            "Loaded instruments page %s; page_count=%s next_cursor_present=%s.",
            page_number,
            len(page_instruments),
            bool(next_cursor),
        )

        if not next_cursor:
            break

        if next_cursor in seen_cursors:
            logger.warning("Stopping instrument pagination because cursor repeated.")
            break

        seen_cursors.add(next_cursor)
        cursor = next_cursor
        page_number += 1

    logger.info("Total raw instruments after pagination: %s.", len(all_instruments))
    return all_instruments


def _extract_result_list(response: Any) -> list[Any]:
    """Extract the Bybit V5 ``result.list`` payload safely."""
    logger = _get_filtering_logger()
    # Bybit V5 public metadata responses are expected to be dictionaries with
    # tradable instrument rows under result.list.
    if not isinstance(response, dict):
        logger.warning("Skipping instruments response; response_type=%s.", type(response).__name__)
        return []

    result = response.get("result")
    if not isinstance(result, dict):
        logger.warning("Skipping instruments response with missing result object.")
        return []

    raw_instruments = result.get("list")
    if not isinstance(raw_instruments, list):
        logger.warning("Skipping instruments response with missing result list.")
        return []

    return raw_instruments


def _extract_next_page_cursor(response: Any) -> str | None:
    """Extract Bybit V5 result.nextPageCursor safely."""
    if not isinstance(response, dict):
        return None

    result = response.get("result")
    if not isinstance(result, dict):
        return None

    next_cursor = result.get("nextPageCursor")
    if not isinstance(next_cursor, str) or not next_cursor:
        return None

    return next_cursor


def _is_usdt_contract(instrument: dict[str, Any]) -> bool:
    """Return True when Bybit identifies the contract as USDT-settled."""
    quote_coin = instrument.get("quoteCoin")
    settle_coin = instrument.get("settleCoin")
    return quote_coin == "USDT" or settle_coin == "USDT"


def _has_required_metadata(instrument: dict[str, Any], symbol: str) -> bool:
    """Return True when fields required for universe filtering are present."""
    logger = _get_filtering_logger()
    if instrument.get("quoteCoin") is None and instrument.get("settleCoin") is None:
        logger.warning("Skipping malformed instrument %s with missing quote and settle coin.", symbol)
        return False
    if instrument.get("contractType") is None:
        logger.warning("Skipping malformed instrument %s with missing contract type.", symbol)
        return False
    if instrument.get("status") is None:
        logger.warning("Skipping malformed instrument %s with missing status.", symbol)
        return False
    return True


def _is_perpetual_contract(instrument: dict[str, Any]) -> bool:
    """Return True for Bybit linear perpetual futures contracts."""
    contract_type = instrument.get("contractType")
    return contract_type in {"LinearPerpetual", "PERPETUAL", "Perpetual"}


def _is_active_instrument(instrument: dict[str, Any]) -> bool:
    """Return True when the instrument is currently tradable."""
    status = instrument.get("status")
    return status == "Trading"


def _get_filtering_logger() -> logging.Logger:
    """Return the configured filtering logger."""
    return get_loggers()["filtering"]
