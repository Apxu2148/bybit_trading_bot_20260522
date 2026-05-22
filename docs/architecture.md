# Architecture Overview

## Project Goal

`bybit_trading_bot_20260522` is a future Python trading bot for Bybit USDT perpetual futures. The final bot is expected to load market data, select target leverage through a replaceable strategy module, build a rebalance plan, and execute the plan through limit orders.

Stage 1 is infrastructure only. It creates the package layout, configuration, logging, runtime state management, placeholder modules, and tests. It does not implement real Bybit API calls, real order placement, or trading logic.

## Module List

- `config/config.py`: Central project settings and placeholder safety parameters.
- `secrets/api_keys.example.py`: Template for local Bybit API credentials.
- `bybit/client.py`: Future REST client boundary.
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

## Stage 1 Status

Implemented:

- Project skeleton.
- Central config constants.
- Credential example file.
- Logger setup with rotating files.
- JSON state manager.
- Placeholder modules with documented future responsibilities.
- Pytest configuration and base tests.

Not implemented:

- Real Bybit API calls.
- Real order placement.
- Trading strategy logic.
- Rebalance planning business logic.
- Docker files.
