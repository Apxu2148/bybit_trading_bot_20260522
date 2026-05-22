# bybit_trading_bot_20260522

Stage 1 skeleton for a future Python trading bot for Bybit USDT perpetual futures.

This stage contains project infrastructure only: configuration, logging, JSON state storage, placeholder modules, and tests. Real Bybit API calls, order placement, and trading logic are not implemented yet.

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

## Run

```powershell
python main.py
```

The entry point initializes loggers, loads JSON state, and prints that the Stage 1 skeleton is ready. It does not connect to Bybit.

## Tests

```powershell
pytest
```

## Structure

```text
config/          Project-level constants.
secrets/         Example API key file; real credentials stay ignored.
bybit/           Future Bybit REST client boundary.
market_data/     Future instrument, candle, and filter modules.
strategy/        Replaceable target-leverage strategy modules.
portfolio/       Future position reading and rebalance planning.
execution/       Future order, leverage, rebalance, and cleanup modules.
risk/            Future risk engine boundary.
triggers/        Future rebalance trigger boundary.
state/           JSON runtime state files.
logging_setup/   Reusable logger setup.
utils/           Future shared helpers.
tests/           Pytest test suite.
```
