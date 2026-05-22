"""Future time utilities for UTC timestamps and candle completeness.

Later stages may use this module to provide UTC timestamps, determine candle
age, and decide whether the latest candle should be included using the 50% rule
documented in market_data/candles.py.

Stage 1 does not need runtime time helpers beyond these documented boundaries.
"""
