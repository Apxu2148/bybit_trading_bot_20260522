"""Future rebalance plan builder.

Later stages will receive current positions and target leverage, convert target
leverage to target position quantity using the latest close price, and calculate
delta quantity for each symbol.

If a delta's notional value is below MIN_ORDER_NOTIONAL_USDT, the future logic
should set that delta quantity to zero so tiny orders are not sent to Bybit.

Stage 1 does not implement business logic.
"""
