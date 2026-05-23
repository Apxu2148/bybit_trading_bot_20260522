"""Rounding helpers for exchange-safe order values."""

from __future__ import annotations

from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_UP


def round_price_to_tick(price: float, tick_size: float) -> float:
    """Round a price to the nearest valid tick size."""
    tick = _positive_decimal(tick_size, "tick_size")
    price_decimal = Decimal(str(price))
    ticks = (price_decimal / tick).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return float(ticks * tick)


def round_qty_to_step(qty: float, qty_step: float) -> float:
    """Round quantity down by absolute value while preserving sign."""
    return round_qty_abs_down(qty=qty, qty_step=qty_step)


def round_qty_abs_down(qty: float, qty_step: float) -> float:
    """Round signed quantity toward zero by absolute step size."""
    step = _positive_decimal(qty_step, "qty_step")
    qty_decimal = Decimal(str(qty))
    sign = Decimal("-1") if qty_decimal < 0 else Decimal("1")
    abs_qty = abs(qty_decimal)
    steps = (abs_qty / step).to_integral_value(rounding=ROUND_FLOOR)
    return float(sign * steps * step)


def _positive_decimal(value: float, name: str) -> Decimal:
    """Return a positive Decimal or raise ValueError for invalid inputs."""
    decimal_value = Decimal(str(value))
    if decimal_value <= 0:
        raise ValueError(f"{name} must be greater than zero.")
    return decimal_value
