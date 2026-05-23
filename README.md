# bybit_trading_bot_20260522

Stage 9 local bot loop for a Python trading bot for Bybit USDT perpetual futures.

This stage contains project infrastructure, logging, JSON state storage, a thin Bybit REST client wrapper, market data loading, universe filters, a replaceable strategy loader, the default momentum-volatility strategy, portfolio reading, rebalance plan calculation, low-level execution utilities, the MA limit rebalancer, rebalance orchestration, the local main loop, and tests.

## Setup

```powershell
cd C:\Python\bybit_trading_bot_20260522
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Secrets

Copy the example credentials file:

```powershell
Copy-Item secrets\api_keys.example.py secrets\api_keys.py
```

Then edit `secrets/api_keys.py` and fill:

```python
API_KEY = "your_bybit_api_key"
API_SECRET = "your_bybit_api_secret"
```

The real `secrets/api_keys.py` file is ignored by Git.

Never commit real API keys. The Bybit client can run public methods without credentials, but private methods require `secrets/api_keys.py`.

## Run

```powershell
python main.py
```

The entry point starts the local bot loop. It can place real orders when the rebalance trigger fires or when `RUN_REBALANCE_ON_START = 1` and no prior successful rebalance is recorded. Stop it with Ctrl+C for a graceful shutdown.

Runtime state is stored in `state/bot_state.json`. Logs are written under `logs/`.

For manual read-only strategy verification, run:

```powershell
python temp_test_strategy.py
```

For manual read-only portfolio and rebalance-plan verification, run:

```powershell
python temp_test_portfolio_rebalance_plan.py
```

An optional live execution smoke test exists, but it may place real orders and requires an exact typed confirmation:

```powershell
python temp_test_execution_manual.py
```

An optional live MA limit rebalancer test also exists and requires its own exact confirmation:

```powershell
python temp_test_limit_rebalancer_manual.py
```

An optional live rebalance orchestrator test exists and requires explicit confirmations:

```powershell
python temp_test_rebalance_orchestrator_manual.py
```

An optional one-cycle local bot test exists and requires explicit confirmation:

```powershell
python temp_test_run_once_manual.py
```

## Tests

```powershell
pytest
```

## Structure

```text
config/          Project-level constants.
secrets/         Example API key file; real credentials stay ignored.
bybit/           Bybit REST client wrapper boundary.
market_data/     Instrument discovery, candle loading, and universe filters.
strategy/        Strategy loader and replaceable target-leverage modules.
portfolio/       Position reading and rebalance plan calculation.
execution/       Low-level execution, limit rebalancing, and orchestration modules.
risk/            Future risk engine boundary.
triggers/        Equity rebalance trigger helpers.
state/           JSON runtime state files.
logging_setup/   Reusable logger setup.
utils/           Shared helpers, including exchange rounding.
tests/           Pytest test suite.
```
