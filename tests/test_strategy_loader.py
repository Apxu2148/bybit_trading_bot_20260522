from __future__ import annotations

import sys
from types import ModuleType

import pytest
from pytest import MonkeyPatch

from strategy.loader import (
    StrategyFunctionMissingError,
    StrategyLoadError,
    get_target_leverage_function,
    load_target_leverage_module,
)


def test_loads_momentum_volatility_from_dotted_path() -> None:
    module = load_target_leverage_module("strategy.momentum_volatility")

    assert module.__name__ == "strategy.momentum_volatility"


def test_returns_callable_calculate_target_leverage() -> None:
    function = get_target_leverage_function("strategy.momentum_volatility")

    assert callable(function)


def test_raises_clear_exception_for_missing_module() -> None:
    with pytest.raises(StrategyLoadError, match="Could not import strategy module"):
        load_target_leverage_module("strategy.module_that_does_not_exist")


def test_raises_clear_exception_when_function_is_missing() -> None:
    with pytest.raises(StrategyFunctionMissingError, match="calculate_target_leverage"):
        get_target_leverage_function("config.config")


def test_raises_clear_exception_when_function_is_not_callable(monkeypatch: MonkeyPatch) -> None:
    module_name = "fake_strategy_non_callable"
    module = ModuleType(module_name)
    module.calculate_target_leverage = 1.0  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, module_name, module)

    with pytest.raises(StrategyFunctionMissingError, match="not callable"):
        get_target_leverage_function(module_name)
