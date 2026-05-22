from __future__ import annotations

import importlib
from pathlib import Path


def test_key_modules_can_be_imported() -> None:
    modules = [
        "config.config",
        "secrets",
        "bybit.client",
        "market_data.instruments",
        "market_data.candles",
        "market_data.filters",
        "strategy.momentum_volatility",
        "portfolio.positions",
        "portfolio.rebalance_plan",
        "execution.orders",
        "execution.leverage_manager",
        "execution.limit_rebalancer",
        "execution.cleanup",
        "risk.risk_engine",
        "triggers.rebalance_trigger",
        "state.state_manager",
        "logging_setup.logger",
        "utils.rounding",
        "utils.time_utils",
    ]

    for module_name in modules:
        importlib.import_module(module_name)


def test_api_keys_example_file_exists() -> None:
    assert Path("secrets/api_keys.example.py").exists()
