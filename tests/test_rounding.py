from __future__ import annotations

import pytest

from utils.rounding import round_price_to_tick, round_qty_abs_down, round_qty_to_step


def test_price_rounds_to_tick() -> None:
    assert round_price_to_tick(100.03, 0.05) == pytest.approx(100.05)
    assert round_price_to_tick(100.02, 0.05) == pytest.approx(100.0)


def test_qty_rounds_down_to_step() -> None:
    assert round_qty_to_step(1.29, 0.1) == pytest.approx(1.2)


def test_signed_qty_keeps_sign() -> None:
    assert round_qty_to_step(-1.29, 0.1) == pytest.approx(-1.2)
    assert round_qty_abs_down(-0.049, 0.01) == pytest.approx(-0.04)


def test_invalid_step_raises_value_error() -> None:
    with pytest.raises(ValueError):
        round_qty_to_step(1.0, 0.0)
    with pytest.raises(ValueError):
        round_price_to_tick(1.0, -0.01)


def test_doge_like_price_and_qty_values_round_to_exchange_steps() -> None:
    assert round_price_to_tick(0.10105400000000002, 0.00001) == pytest.approx(0.10105)
    assert round_qty_abs_down(98.85465960644714, 1.0) == pytest.approx(98.0)
