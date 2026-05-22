# Architecture Overview

## Project Goal

`bybit_trading_bot_20260522` is a future Python trading bot for Bybit USDT perpetual futures. The final bot is expected to load market data, select target leverage through a replaceable strategy module, build a rebalance plan, and execute the plan through limit orders.

Stage 3 adds a thin Bybit REST client wrapper on top of the infrastructure created earlier. It still does not implement trading strategy logic, real order execution flows, or Docker files.

## Module List

- `config/config.py`: Central project settings and placeholder safety parameters.
- `secrets/api_keys.example.py`: Template for local Bybit API credentials.
- `bybit/client.py`: The only low-level Bybit REST wrapper.
- `market_data/instruments.py`: Future Bybit USDT perpetual futures discovery.
- `market_data/candles.py`: Future candle loading and latest-candle completeness rules.
- `market_data/filters.py`: Future eligibility filters and exclusion logging.
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

## Stage 3 Status

Implemented:

- Project skeleton.
- Central config constants.
- Credential example file.
- Logger setup with rotating files.
- JSON state manager.
- Placeholder modules with documented future responsibilities.
- Bybit REST client wrapper foundation with pybit.
- Pytest configuration and base tests.

Not implemented:

- Trading strategy logic.
- Real order execution flows.
- Rebalance planning business logic.
- Docker files.
