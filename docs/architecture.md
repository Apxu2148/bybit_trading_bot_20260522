# Architecture Overview

## Project Goal

`bybit_trading_bot_20260522` is a future Python trading bot for Bybit USDT perpetual futures. The final bot is expected to load market data, select target leverage through a replaceable strategy module, build a rebalance plan, and execute the plan through limit orders.

Stage 8 adds rebalance orchestration on top of the strategy, portfolio, planning, and execution layers. It still does not integrate this orchestration into the main trading loop or Docker files.

## Module List

- `config/config.py`: Central project settings and placeholder safety parameters.
- `secrets/api_keys.example.py`: Template for local Bybit API credentials.
- `bybit/client.py`: The only low-level Bybit REST wrapper.
- `market_data/instruments.py`: Bybit USDT perpetual futures discovery from public instrument metadata.
- `market_data/candles.py`: Public kline loading, candle normalization, sorting, and latest-candle completeness rules.
- `market_data/filters.py`: Config-driven eligibility filters and exclusion logging.
- `strategy/loader.py`: Replaceable strategy module loader for `TARGET_LEVERAGE_MODULE`.
- `strategy/momentum_volatility.py`: Default momentum-volatility target leverage strategy.
- `portfolio/positions.py`: Read-only current-position and exchange-equity reader.
- `portfolio/rebalance_plan.py`: Target-position and delta-quantity plan builder.
- `execution/orders.py`: Low-level order intent helpers for limit, market, cancel-all, and open-order reads.
- `execution/leverage_manager.py`: Leverage candidate and best-effort cross-margin helpers.
- `execution/limit_rebalancer.py`: MA-based limit-order rebalance executor.
- `execution/rebalance_orchestrator.py`: High-level bridge from target leverage to rebalance execution.
- `execution/cleanup.py`: Small leftover position cleanup helper.
- `risk/risk_engine.py`: Placeholder for future risk stops.
- `triggers/rebalance_trigger.py`: Future rebalance trigger rules.
- `state/state_manager.py`: Runtime JSON state persistence.
- `logging_setup/logger.py`: Main, execution, and filtering logger setup.
- `utils/rounding.py`: Tick-size and quantity-step rounding helpers.
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

`config.py` stores shared parameters. `TARGET_LEVERAGE_MODULE` selects the strategy module dynamically through its dotted Python module path. The default is:

```python
"strategy.momentum_volatility"
```

`strategy/loader.py` imports this module with `importlib.import_module`, verifies that it exposes a callable `calculate_target_leverage(...)`, and raises clear strategy-loader exceptions when the module or function is invalid.

The selected strategy module forms a target leverage dictionary such as:

```python
{"SOLUSDT": 1.0}
```

or:

```python
{"SOLUSDT": -1.0}
```

`positions.py` reads current positions from Bybit and normalizes them. `rebalance_plan.py` converts target leverage to target quantity using the latest close price, then calculates delta quantity. `limit_rebalancer.py` can execute a signed delta quantity through moving-average-based limit orders. `orders.py` contains the low-level order operations that future execution flows can call.

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

## Strategy Flow

Every replaceable strategy module must expose:

```python
calculate_target_leverage(...) -> dict[str, float]
```

The default `strategy/momentum_volatility.py` receives eligible symbols and hourly candles, scores each symbol over the latest `SCORE_LOOKBACK_HOURS` candles, and selects the one symbol with the largest absolute score.

The score formula is:

```text
score = trend * abs(trend) / volatility
```

Where:

- `trend = ln(close_last / close_first)`
- `volatility = standard deviation of hourly log returns`
- hourly log return `r_i = ln(close_i / close_{i-1})`

If volatility is zero, candles are malformed, prices are non-positive, or there is not enough history, the symbol is skipped. The strategy supports internal direction modes: `long_and_short`, `long_only`, and `short_only`.

The strategy output is:

```python
target_leverage: dict[str, float]
```

Examples:

```python
{"BTCUSDT": 1.0}
{"SOLUSDT": -1.0}
{}
```

This is a target map only. Strategy calculation does not place orders or modify exchange state.

## Portfolio And Rebalance Planning

`portfolio/positions.py` uses `BybitClient` read-only private endpoints to parse:

- current linear positions as signed quantities, where long positions are positive and short positions are negative;
- exchange equity from wallet balance, preferring account-level `totalEquity` and falling back to USDT coin equity or `usdValue`;
- total equity as `exchange_equity + RESERVE_BALANCE_USDT`.

Current leverage is not calculated. The project compares current position quantity and target position quantity directly.

`portfolio/rebalance_plan.py` converts strategy output into target quantities:

```text
target_notional = target_leverage[symbol] * total_equity
target_qty = target_notional / last_close_price
```

It then aligns current and target position dictionaries by symbol and calculates:

```text
delta_qty = target_qty - current_qty
```

If `abs(delta_qty * last_close_price) < MIN_ORDER_NOTIONAL_USDT`, the ordinary rebalance delta is set to `0.0`. This prevents planning tiny normal rebalance orders. The rule does not cover future cleanup logic for small leftover positions.

The rebalance plan output contains:

```python
{
    "target_positions": dict[str, float],
    "current_positions_aligned": dict[str, float],
    "target_positions_aligned": dict[str, float],
    "delta_qty": dict[str, float],
}
```

This is a calculation artifact only. Rebalance planning does not place orders, cancel orders, or change leverage.

## Low-Level Execution Utilities

`utils/rounding.py` provides exchange-safe rounding helpers:

- prices round to the nearest tick size;
- quantities round down by absolute value to avoid exceeding intended exposure;
- signed quantities keep their sign.

`execution/orders.py` maps signed quantity deltas to Bybit sides: positive quantities are `Buy`, negative quantities are `Sell`, and zero quantities are rejected. It sends absolute quantities through `BybitClient.place_order`, and also wraps `cancel_all_orders` and `get_open_orders` for one linear symbol.

`execution/leverage_manager.py` tries configured leverage candidates from `LEVERAGE_CANDIDATES` in order and returns the first accepted value. If all candidates fail, it logs a warning and returns `None`. Its cross-margin helper is best-effort and returns `False` if Bybit rejects or does not support the request.

`execution/cleanup.py` is for future tiny leftover positions. It finds positions below `MIN_POSITION_NOTIONAL_USDT`, tries normal market closes first, then reduce-only market closes, and returns a summary of `closed`, `failed`, and `skipped` symbols. Cleanup is only called by orchestration when `ENABLE_SMALL_POSITION_CLEANUP == 1`.

## MA Limit Rebalancer

`execution/limit_rebalancer.py` changes a position by a signed `qty_delta` using recent one-minute candles and a simple moving average. Positive `qty_delta` means buy; negative `qty_delta` means sell.

For buys, the rebalancer waits until the latest usable one-minute close is above the moving average, then places a limit buy at the moving average price. For sells, it waits until the latest usable close is below the moving average, then places a limit sell at the moving average price. The minute candles come from `market_data/candles.py`, so the centralized unfinished-candle rule still applies.

Before each limit order is placed, the rebalancer loads Bybit instrument metadata through `market_data/instruments.py`, extracts `priceFilter.tickSize` and `lotSizeFilter.qtyStep`, rounds the MA price to the tick size, and rounds signed remaining quantity down by absolute quantity step. If metadata is unavailable or the rounded quantity is zero, it does not place an unrounded order.

After each order attempt, the rebalancer sleeps for `LIMIT_ORDER_CHECK_INTERVAL_SECONDS`, cancels open orders for the symbol, rereads the current position, recalculates the remaining delta, and repeats. This handles partial fills by comparing the live current position to the fixed target position instead of assuming an order filled completely.

The module has process-local active-symbol protection through `ACTIVE_REBALANCE_SYMBOLS`. Starting a second rebalance for the same symbol raises `RebalanceAlreadyActiveError`, and a `finally` block removes the symbol when the function exits.

If `ENABLE_MAX_REBALANCE_DURATION == 1`, the rebalancer stops after `MAX_REBALANCE_DURATION_SECONDS`, cancels open orders for the symbol, and returns status `"timeout"`. If the flag is `0`, no timeout is applied.

The rebalancer is available as a reusable function and is not wired directly into `main.py`.

## Rebalance Orchestration

`execution/rebalance_orchestrator.py` bridges strategy output and execution. It receives `target_leverage`, reads exchange equity, adds `RESERVE_BALANCE_USDT`, reads current positions, loads hourly last-close prices for required symbols, builds a rebalance plan, cancels open orders, executes non-zero deltas sequentially through `rebalance_by_limit_order`, cancels open orders again, and optionally runs small-position cleanup.

The orchestration flow is:

```text
target_leverage
  -> target_positions
  -> delta_qty
  -> MA limit rebalancer
```

An empty target map, `target_leverage = {}`, means no desired exposure. Existing current positions are converted into close-position deltas by the rebalance plan.

Leverage preparation is only requested when target absolute exposure is greater than current absolute exposure:

```text
abs(target_position_qty) > abs(current_position_qty)
```

This prepares leverage for opening or increasing exposure and skips leverage preparation when reducing or closing exposure. Flips prepare leverage only when the target side has greater absolute size than the current side.

Stage 8 still does not create automatic live-trading behavior. `run_rebalance(...)` is reusable and manually callable, but it is not wired into `main.py`.

## Stage 8 Status

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
- Replaceable strategy module loader.
- Momentum-volatility target leverage strategy.
- Read-only current position and exchange equity parsing.
- Rebalance plan calculation from target leverage and last close prices.
- Low-level order helper functions.
- Leverage candidate and best-effort margin helpers.
- Small-position cleanup helper.
- Exchange rounding helpers.
- MA-based limit rebalancer with active-symbol protection and optional timeout.
- Rebalance orchestration from target leverage to sequential delta execution.
- Pytest configuration and base tests.

Not implemented:

- Main trading loop.
- Docker files.
