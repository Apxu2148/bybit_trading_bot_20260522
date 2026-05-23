# Architecture Overview

## Project Goal

`bybit_trading_bot_20260522` is a future Python trading bot for Bybit USDT perpetual futures. The final bot is expected to load market data, select target leverage through a replaceable strategy module, build a rebalance plan, and execute the plan through limit orders.

Stage 4 adds read-only market data loading and universe filtering on top of the infrastructure created earlier. It still does not implement trading strategy logic, real order execution flows, or Docker files.

## Module List

- `config/config.py`: Central project settings and placeholder safety parameters.
- `secrets/api_keys.example.py`: Template for local Bybit API credentials.
- `bybit/client.py`: The only low-level Bybit REST wrapper.
- `market_data/instruments.py`: Bybit USDT perpetual futures discovery from public instrument metadata.
- `market_data/candles.py`: Public kline loading, candle normalization, sorting, and latest-candle completeness rules.
- `market_data/filters.py`: Config-driven eligibility filters and exclusion logging.
- `strategy/momentum_volatility.py`: Placeholder strategy selected by default.
- `portfolio/positions.py`: Future current-position reader.
- `portfolio/rebalance_plan.py`: Future conversion from target leverage to delta quantity.
- `execution/orders.py`: Future low-level order operations.
- `execution/leverage_manager.py`: Future leverage and cross-margin setup.
- `execution/limit_rebalancer.py`: Future MA-based limit-order rebalance executor.
- `execution/cleanup.py`: Future cleanup for small leftover positions.
- `risk/risk_engine.py`: Placeholder for future risk stops.
- `triggers/rebalance_trigger.py`: Future rebalance trigger rules.
- `state/state_manager.py`: Runtime JSON state persistence.
- `logging_setup/logger.py`: Main, execution, and filtering logger setup.
- `utils/rounding.py`: Future tick-size and quantity-step helpers.
- `utils/time_utils.py`: Future UTC timestamp and candle-age helpers.

## Future Interaction Flow

```text
rebalance_trigger.py
  -> selected strategy module from TARGET_LEVERAGE_MODULE
  -> positions.py
  -> rebalance_plan.py
  -> limit_rebalancer.py
  -> orders.py
```

`config.py` stores shared parameters. `TARGET_LEVERAGE_MODULE` selects the strategy module dynamically through its dotted Python module path. The selected strategy module must expose `calculate_target_leverage(...)`.

The selected strategy module forms a target leverage dictionary such as:

```python
{"SOLUSDT": 1.0}
```

or:

```python
{"SOLUSDT": -1.0}
```

`positions.py` will read current positions from Bybit and normalize them. `rebalance_plan.py` will convert target leverage to target quantity using the latest close price, then calculate delta quantity. `limit_rebalancer.py` will execute delta quantity through moving-average-based limit orders. `orders.py` will contain low-level order operations.

Before order execution starts, `leverage_manager.py` will try to enable cross margin if possible and set the highest accepted leverage from `LEVERAGE_CANDIDATES`.

`state_manager.py` stores runtime JSON state in `state/bot_state.json`. `logger.py` configures separate log files for main lifecycle messages, execution messages, and filtering messages.

## Bybit Client Boundary

`bybit/client.py` is the only module that should import or call `pybit` directly. Other modules must use `BybitClient` methods instead of constructing their own exchange sessions. This isolates exchange-specific authentication, retry behavior, rate-limit preparation, logging rules, and API parameter naming in one place.

Public market methods can run without API credentials when Bybit allows anonymous access. Private account and order-related methods require `secrets/api_keys.py`; if credentials are missing, the wrapper raises a clear `MissingBybitCredentialsError`.

The wrapper must never log API keys, API secrets, signatures, or full request headers.

## Market Data Flow

`market_data/instruments.py` calls `BybitClient.get_instruments_info(category="linear")`, reads the Bybit V5 `result.list` payload, and keeps only instruments that are USDT-settled or USDT-quoted linear perpetual contracts with `status == "Trading"`. Malformed rows are logged and skipped.

`market_data/candles.py` calls `BybitClient.get_kline(category="linear", ...)`, normalizes Bybit kline rows into dictionaries with `start_time_ms`, OHLC, `volume`, and `turnover`, then sorts candles by `start_time_ms` ascending.

The latest candle rule is mandatory across market data consumers: the newest candle is included only after more than 50 percent of its interval has elapsed. If 50 percent or less has elapsed, that candle is excluded from calculations.

`market_data/filters.py` receives symbols and hourly candles, then applies active config filters: minimum history, average hourly turnover, stablecoin price range, blacklist, optional spread, optional funding rate, and optional EMA distance. The output is:

```python
eligible_symbols: list[str]
```

This list contains Bybit USDT perpetual symbols that passed all active filters. Filter exclusions and the final count are written through the existing filtering logger.

## Stage 4 Status

Implemented:

- Project skeleton.
- Central config constants.
- Credential example file.
- Logger setup with rotating files.
- JSON state manager.
- Bybit REST client wrapper foundation with pybit.
- Public instrument discovery for active USDT perpetual futures.
- Public candle loading, normalization, sorting, and unfinished-candle filtering.
- Config-driven market universe filters with filtering logs.
- Pytest configuration and base tests.

Not implemented:

- Trading strategy logic.
- Real order execution flows.
- Rebalance planning business logic.
- Docker files.
