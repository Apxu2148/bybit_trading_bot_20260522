"""Replaceable strategy module loader."""

from __future__ import annotations

import importlib
from types import ModuleType
from typing import Any, Callable


class StrategyLoadError(Exception):
    """Raised when a strategy module cannot be imported."""


class StrategyFunctionMissingError(StrategyLoadError):
    """Raised when a strategy module does not expose the required function."""


def load_target_leverage_module(module_path: str) -> Any:
    """Import and return a target-leverage strategy module by dotted path."""
    try:
        return importlib.import_module(module_path)
    except ImportError as exc:
        raise StrategyLoadError(f"Could not import strategy module '{module_path}'.") from exc


def get_target_leverage_function(module_path: str) -> Callable[..., dict[str, float]]:
    """Return a strategy module's callable calculate_target_leverage function."""
    module = load_target_leverage_module(module_path)
    function = _get_calculate_target_leverage(module, module_path)
    if not callable(function):
        raise StrategyFunctionMissingError(
            f"Strategy module '{module_path}' has calculate_target_leverage, but it is not callable."
        )
    return function


def _get_calculate_target_leverage(module: ModuleType, module_path: str) -> Any:
    """Return calculate_target_leverage or raise a clear strategy error."""
    if not hasattr(module, "calculate_target_leverage"):
        raise StrategyFunctionMissingError(
            f"Strategy module '{module_path}' must expose calculate_target_leverage(...)."
        )
    return getattr(module, "calculate_target_leverage")
