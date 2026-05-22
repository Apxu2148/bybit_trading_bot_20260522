"""Future candle loading utilities.

Later stages will load candles for a symbol and timeframe through the Bybit
REST API. The latest candle must always be treated as potentially unfinished.

The intended rule is:

* include the latest candle only if more than 50% of its period has passed;
* otherwise exclude it from calculations;
* keep this decision centralized so strategies and filters use consistent data.

Stage 1 does not implement real API calls or candle processing logic.
"""
