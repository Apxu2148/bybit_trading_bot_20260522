"""Market universe filters for Bybit USDT perpetual futures."""

from __future__ import annotations

import logging
from typing import Any

from bybit.client import BybitClient
from config import config
from logging_setup.logger import get_loggers
from market_data.candles import get_hourly_candles, get_last_close


def get_eligible_symbols(
    client: BybitClient,
    symbols: list[str],
) -> list[str]:
    """Load required market data and return symbols that pass active filters."""
    logger = _get_filtering_logger()
    candles_by_symbol: dict[str, list[dict[str, Any]]] = {}
    last_close_by_symbol: dict[str, float] = {}
    candle_limit = max(int(config.SCORE_LOOKBACK_HOURS) + 1, 1)

    for symbol in symbols:
        try:
            candles = get_hourly_candles(client=client, symbol=symbol, limit=candle_limit)
        except Exception as exc:
            logger.warning(
                "Excluding %s because hourly candles could not be loaded; error_type=%s.",
                symbol,
                exc.__class__.__name__,
            )
            candles = []

        candles_by_symbol[symbol] = candles
        last_close = get_last_close(candles)
        if last_close is not None:
            last_close_by_symbol[symbol] = last_close

    tickers_by_symbol = _load_tickers_by_symbol(client) if _ticker_filters_enabled() else None
    return apply_filters(
        symbols=symbols,
        candles_by_symbol=candles_by_symbol,
        last_close_by_symbol=last_close_by_symbol,
        tickers_by_symbol=tickers_by_symbol,
    )


def apply_filters(
    symbols: list[str],
    candles_by_symbol: dict[str, list[dict[str, Any]]],
    last_close_by_symbol: dict[str, float],
    tickers_by_symbol: dict[str, dict[str, Any]] | None = None,
) -> list[str]:
    """Apply active config-driven market filters to a prepared data set."""
    logger = _get_filtering_logger()
    eligible_symbols: list[str] = []
    blacklist = {symbol.upper() for symbol in config.SYMBOL_BLACKLIST}

    for symbol in symbols:
        normalized_symbol = symbol.upper()
        candles = candles_by_symbol.get(symbol, [])

        if normalized_symbol in blacklist:
            logger.info("Excluding %s by blacklist.", symbol)
            continue

        lookback_candles = _get_lookback_candles(candles)
        if len(lookback_candles) < config.SCORE_LOOKBACK_HOURS:
            logger.info(
                "Excluding %s by insufficient history; candles=%s required=%s.",
                symbol,
                len(lookback_candles),
                config.SCORE_LOOKBACK_HOURS,
            )
            continue

        avg_hourly_turnover = _average_turnover(lookback_candles)
        if avg_hourly_turnover is None or avg_hourly_turnover < config.MIN_AVG_HOURLY_VOLUME:
            logger.info(
                "Excluding %s by volume; avg_hourly_turnover=%s required=%s.",
                symbol,
                avg_hourly_turnover,
                config.MIN_AVG_HOURLY_VOLUME,
            )
            continue

        last_close = _to_float(last_close_by_symbol.get(symbol))
        if last_close is None:
            logger.info("Excluding %s because last close is unavailable.", symbol)
            continue

        if _stablecoin_price_filter_enabled() and _is_stablecoin_price(last_close):
            logger.info("Excluding %s by stablecoin price filter; last_close=%s.", symbol, last_close)
            continue

        ticker = (tickers_by_symbol or {}).get(symbol)
        if _spread_filter_enabled() and _is_excluded_by_spread(symbol, ticker):
            continue

        if _funding_filter_enabled() and _is_excluded_by_funding(symbol, ticker):
            continue

        if _ema_distance_filter_enabled() and _is_excluded_by_ema_distance(symbol, lookback_candles, last_close):
            continue

        eligible_symbols.append(symbol)

    logger.info("Final eligible symbol count: %s.", len(eligible_symbols))
    return eligible_symbols


def _load_tickers_by_symbol(client: BybitClient) -> dict[str, dict[str, Any]]:
    """Load public linear tickers and return them keyed by symbol."""
    logger = _get_filtering_logger()
    try:
        response = client.get_tickers(category="linear")
    except Exception as exc:
        logger.warning("Ticker data unavailable; error_type=%s.", exc.__class__.__name__)
        return {}

    tickers: dict[str, dict[str, Any]] = {}
    for raw_ticker in _extract_result_list(response, "tickers"):
        if not isinstance(raw_ticker, dict):
            logger.warning("Skipping malformed ticker row; row_type=%s.", type(raw_ticker).__name__)
            continue

        symbol = raw_ticker.get("symbol")
        if not isinstance(symbol, str) or not symbol:
            logger.warning("Skipping malformed ticker with missing symbol.")
            continue

        tickers[symbol] = dict(raw_ticker)

    return tickers


def _extract_result_list(response: Any, label: str) -> list[Any]:
    """Extract a Bybit V5 ``result.list`` payload safely."""
    logger = _get_filtering_logger()
    if not isinstance(response, dict):
        logger.warning("Skipping %s response; response_type=%s.", label, type(response).__name__)
        return []

    result = response.get("result")
    if not isinstance(result, dict):
        logger.warning("Skipping %s response with missing result object.", label)
        return []

    raw_items = result.get("list")
    if not isinstance(raw_items, list):
        logger.warning("Skipping %s response with missing result list.", label)
        return []

    return raw_items


def _get_lookback_candles(candles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return the latest configured number of candles with valid turnover."""
    valid_candles = [
        candle
        for candle in candles
        if isinstance(candle, dict) and _to_float(candle.get("turnover")) is not None
    ]
    return valid_candles[-int(config.SCORE_LOOKBACK_HOURS) :]


def _average_turnover(candles: list[dict[str, Any]]) -> float | None:
    """Return average hourly turnover for a prepared lookback window."""
    turnovers = [_to_float(candle.get("turnover")) for candle in candles]
    valid_turnovers = [turnover for turnover in turnovers if turnover is not None]
    if not valid_turnovers:
        return None
    return sum(valid_turnovers) / len(valid_turnovers)


def _is_stablecoin_price(last_close: float) -> bool:
    """Return True when price is inside configured stablecoin-like bounds."""
    return config.STABLECOIN_PRICE_LOWER_BOUND <= last_close <= config.STABLECOIN_PRICE_UPPER_BOUND


def _is_excluded_by_spread(symbol: str, ticker: dict[str, Any] | None) -> bool:
    """Return True when ticker bid/ask spread exceeds the configured maximum."""
    logger = _get_filtering_logger()
    if ticker is None:
        logger.info("Spread data unavailable for %s; skipping spread filter.", symbol)
        return False

    bid = _to_float(ticker.get("bid1Price", ticker.get("bidPrice")))
    ask = _to_float(ticker.get("ask1Price", ticker.get("askPrice")))
    if bid is None or ask is None or bid <= 0 or ask <= 0 or ask < bid:
        logger.info("Spread data unavailable for %s; skipping spread filter.", symbol)
        return False

    mid_price = (bid + ask) / 2
    spread_pct = (ask - bid) / mid_price
    if spread_pct > config.MAX_SPREAD_PCT:
        logger.info("Excluding %s by spread; spread_pct=%s max=%s.", symbol, spread_pct, config.MAX_SPREAD_PCT)
        return True

    return False


def _is_excluded_by_funding(symbol: str, ticker: dict[str, Any] | None) -> bool:
    """Return True when absolute funding rate exceeds the configured maximum."""
    logger = _get_filtering_logger()
    if ticker is None:
        logger.info("Funding data unavailable for %s; skipping funding filter.", symbol)
        return False

    funding_rate = _to_float(ticker.get("fundingRate"))
    if funding_rate is None:
        logger.info("Funding data unavailable for %s; skipping funding filter.", symbol)
        return False

    abs_funding_rate = abs(funding_rate)
    if abs_funding_rate > config.MAX_ABS_FUNDING_RATE:
        logger.info(
            "Excluding %s by funding; abs_funding_rate=%s max=%s.",
            symbol,
            abs_funding_rate,
            config.MAX_ABS_FUNDING_RATE,
        )
        return True

    return False


def _is_excluded_by_ema_distance(
    symbol: str,
    candles: list[dict[str, Any]],
    last_close: float,
) -> bool:
    """Return True when price is too far from its EMA baseline."""
    logger = _get_filtering_logger()
    period = int(config.EMA_DISTANCE_PERIOD)
    closes = [_to_float(candle.get("close")) for candle in candles]
    valid_closes = [close for close in closes if close is not None]

    if period <= 0 or len(valid_closes) < period:
        logger.info(
            "Excluding %s by EMA distance; candles=%s required=%s.",
            symbol,
            len(valid_closes),
            period,
        )
        return True

    ema = _calculate_ema(valid_closes[-period:], period)
    if ema is None or ema == 0:
        logger.info("Excluding %s by EMA distance; EMA unavailable.", symbol)
        return True

    distance = abs(last_close / ema - 1)
    if distance > config.MAX_EMA_DISTANCE:
        logger.info("Excluding %s by EMA distance; distance=%s max=%s.", symbol, distance, config.MAX_EMA_DISTANCE)
        return True

    return False


def _calculate_ema(values: list[float], period: int) -> float | None:
    """Calculate an EMA from a sequence of values."""
    if not values or period <= 0:
        return None

    multiplier = 2 / (period + 1)
    ema = values[0]
    for value in values[1:]:
        ema = (value - ema) * multiplier + ema
    return ema


def _ticker_filters_enabled() -> bool:
    """Return True when any ticker-backed filter is active."""
    return _spread_filter_enabled() or _funding_filter_enabled()


def _stablecoin_price_filter_enabled() -> bool:
    """Return True when the stablecoin price filter is active."""
    return config.ENABLE_STABLECOIN_PRICE_FILTER == 1


def _spread_filter_enabled() -> bool:
    """Return True when the spread filter is active."""
    return config.ENABLE_SPREAD_FILTER == 1


def _funding_filter_enabled() -> bool:
    """Return True when the funding filter is active."""
    return config.ENABLE_FUNDING_FILTER == 1


def _ema_distance_filter_enabled() -> bool:
    """Return True when the EMA distance filter is active."""
    return config.ENABLE_EMA_DISTANCE_FILTER == 1


def _to_float(value: Any) -> float | None:
    """Convert a value to float without raising."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _get_filtering_logger() -> logging.Logger:
    """Return the configured filtering logger."""
    return get_loggers()["filtering"]
