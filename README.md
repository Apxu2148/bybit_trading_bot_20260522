# bybit_trading_bot_20260522

Stage 4 foundation for a future Python trading bot for Bybit USDT perpetual futures.

This stage contains project infrastructure, logging, JSON state storage, a thin Bybit REST client wrapper, market data loading, universe filters, and tests. Trading logic and real order execution are not implemented yet.

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

The entry point initializes loggers, loads JSON state, and prints that the infrastructure check is ready. It does not place orders.

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
