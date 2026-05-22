from __future__ import annotations

from config import config


def test_important_config_constants_exist_and_have_basic_types() -> None:
    assert isinstance(config.PROJECT_NAME, str)
    assert isinstance(config.TARGET_LEVERAGE_MODULE, str)
    assert isinstance(config.SCORE_LOOKBACK_HOURS, int)
    assert isinstance(config.MIN_AVG_HOURLY_VOLUME, int)
    assert isinstance(config.REBALANCE_THRESHOLD_PCT, float)
    assert isinstance(config.LEVERAGE_CANDIDATES, list)
    assert isinstance(config.STATE_FILE, str)
    assert isinstance(config.LOG_DIR, str)


def test_target_leverage_module_default() -> None:
    assert config.TARGET_LEVERAGE_MODULE == "strategy.momentum_volatility"


def test_leverage_candidates_are_positive_numbers() -> None:
    assert config.LEVERAGE_CANDIDATES
    assert all(isinstance(value, int) for value in config.LEVERAGE_CANDIDATES)
    assert all(value > 0 for value in config.LEVERAGE_CANDIDATES)
