"""Future rounding helpers for exchange-safe order values.

Later stages will round order prices to tick size and order quantities to the
quantity step required by Bybit. These helpers should be used immediately before
sending order requests so every execution path applies the same exchange rules.

Stage 1 does not implement rounding business logic.
"""
