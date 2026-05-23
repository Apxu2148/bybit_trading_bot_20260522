"""Central project configuration for the Stage 1 Bybit trading bot skeleton.

This module intentionally uses simple Python constants instead of a dynamic
configuration loader. The goal for Stage 1 is to make every important setting
easy to find, easy to review, and easy to import from the rest of the project.

No strategy-specific calculations belong here. The config only selects which
strategy module should be used and defines shared thresholds, paths, and safety
placeholders that later stages may consume.
"""

# Human-readable project name used in logs, documentation, and diagnostics.
PROJECT_NAME = "bybit_trading_bot_20260522"

# Dotted Python module path for the strategy module.
# The selected module must expose calculate_target_leverage(...).
# Change this value to switch trading strategies without changing core bot logic.
TARGET_LEVERAGE_MODULE = "strategy.momentum_volatility"

# Amount of account equity, in USDT, that future position sizing should leave
# unused. Stage 1 does not calculate positions yet, so this is only a placeholder.
RESERVE_BALANCE_USDT = 40.0

# Future multiplier applied to target position sizes. Values above 1.0 would
# amplify target exposure, while values below 1.0 would reduce it.
POSITION_MULTIPLIER = 1.0

# Number of hourly candles future strategy modules may inspect when scoring a
# symbol. Strategy-specific interpretation must remain inside the strategy module.
SCORE_LOOKBACK_HOURS = 100

# Minimum average hourly volume in USDT for a symbol to be considered liquid
# enough by future market filters.
MIN_AVG_HOURLY_VOLUME = 100_000

# Enable or disable the future stablecoin price sanity filter. This is stored
# as 1/0 to keep it easy to edit in plain text and future environment overrides.
ENABLE_STABLECOIN_PRICE_FILTER = 1

# Lower and upper bounds for stablecoin-like instruments. Later filters may use
# these values to exclude assets whose price behaves unlike a stablecoin.
STABLECOIN_PRICE_LOWER_BOUND = 0.9
STABLECOIN_PRICE_UPPER_BOUND = 1.1

# Symbols that must never be selected. Keep uppercase Bybit symbols here, for
# example ["BTCUSDT"], when a market should be excluded manually.
SYMBOL_BLACKLIST = []

# How often the future bot should refresh tradable instruments from Bybit.
INSTRUMENTS_REFRESH_INTERVAL_HOURS = 24

# Moving-average period, in minutes, that future limit-order execution may use
# to choose passive rebalance prices.
LIMIT_MA_PERIOD_MINUTES = 5

# Extra candles to fetch beyond the MA window so that the future execution code
# can tolerate incomplete latest candles and API edge cases.
LIMIT_MA_EXTRA_CANDLES = 5

# Future interval between checks of open limit orders during a rebalance loop.
LIMIT_ORDER_CHECK_INTERVAL_SECONDS = 60

# Future execution safety parameters.
# In Stage 1 these values are placeholders only.
# In later stages, execution/limit_rebalancer.py may use them to stop trying
# to complete a rebalance after a maximum duration.
# Keep ENABLE_MAX_REBALANCE_DURATION = 0 until this logic is implemented and tested.
ENABLE_MAX_REBALANCE_DURATION = 0
MAX_REBALANCE_DURATION_SECONDS = 1800

# Minimum order notional, in USDT. Future rebalance planning should set tiny
# deltas to zero when their notional value is below this threshold.
MIN_ORDER_NOTIONAL_USDT = 5.0

# Enable or disable future cleanup of small leftover positions after rebalancing.
ENABLE_SMALL_POSITION_CLEANUP = 1

# Position notionals below this threshold may be considered small leftovers by
# future cleanup logic.
MIN_POSITION_NOTIONAL_USDT = 5.0

# Maximum attempts for future market-order cleanup of small leftover positions.
SMALL_POSITION_CLEANUP_MAX_MARKET_ATTEMPTS = 10

# Maximum attempts for future reduce-only market-order cleanup if normal market
# cleanup does not fully close a small leftover position.
SMALL_POSITION_CLEANUP_MAX_REDUCE_ONLY_ATTEMPTS = 10

# Maximum number of concurrent API operations that future asynchronous or
# threaded code should allow at once.
API_SEMAPHORE_LIMIT = 5

# Coarse request-rate placeholders for later API throttling. Stage 1 does not
# call Bybit, but these values document intended runtime limits.
MAX_API_REQUESTS_PER_SECOND = 5
MAX_ORDER_REQUESTS_PER_SECOND = 2
MAX_CANCEL_ALL_REQUESTS_PER_SECOND = 0.5

# API_MAX_RETRIES controls how many times failed REST requests are retried.
# Keep this value modest so transient network issues can recover without hiding
# persistent API or authentication problems.
API_MAX_RETRIES = 3

# API_RETRY_DELAY_SECONDS controls the delay between retry attempts. Retry logs
# must never include API keys, API secrets, signatures, or full request headers.
API_RETRY_DELAY_SECONDS = 1.0

# Candidate leverage values used in future stages.
# The bot will try them from left to right and use the first value accepted by Bybit.
# This list is editable because different futures have different maximum leverage.
LEVERAGE_CANDIDATES = [100, 50, 30, 20, 15, 10, 5]

# Minimum relative equity change required before the local bot loop runs a
# rebalance cycle.
REBALANCE_THRESHOLD_PCT = 0.05

# Run one rebalance cycle on local bot startup when no prior successful
# rebalance timestamp exists in state. Set to 0 to wait for the equity
# threshold trigger instead.
RUN_REBALANCE_ON_START = 1

# If no symbol passes filters, the bot loop waits this many minutes before
# checking the universe again.
NO_ELIGIBLE_SYMBOLS_RECHECK_INTERVAL_MINUTES = 60

# Optional future spread filter. It is disabled in Stage 1 because no market
# data or execution logic exists yet.
ENABLE_SPREAD_FILTER = 0
MAX_SPREAD_PCT = 0.003

# Optional future funding-rate filter. It is disabled until funding data and
# filtering behavior are explicitly implemented and tested.
ENABLE_FUNDING_FILTER = 0
MAX_ABS_FUNDING_RATE = 0.005

# Optional future EMA-distance filter. It may be used later to exclude symbols
# whose latest price is too far from an EMA baseline.
ENABLE_EMA_DISTANCE_FILTER = 0
EMA_DISTANCE_PERIOD = 24
MAX_EMA_DISTANCE = 0.12

# Risk engine placeholders for future stages.
# In v1 risk_engine.py is only a placeholder.
# These flags must stay disabled until risk logic is explicitly implemented and tested.
ENABLE_MAX_TOTAL_LOSS_STOP = 0
MAX_TOTAL_LOSS_PCT = 0.30

ENABLE_MAX_24H_LOSS_STOP = 0
MAX_24H_LOSS_PCT = 0.15

ENABLE_MAX_24H_REBALANCES_LIMIT = 0
MAX_24H_REBALANCES = 10

# Directory for log files created by logging_setup/logger.py.
LOG_DIR = "logs"

# Directory and file used by state/state_manager.py for runtime JSON state.
STATE_DIR = "state"
STATE_FILE = "state/bot_state.json"

# Log rotation settings. Rotation keeps log files from growing indefinitely
# while preserving a small number of historical backups.
LOG_ROTATION_ENABLED = 1
LOG_MAX_BYTES = 20_000_000
LOG_BACKUP_COUNT = 3
