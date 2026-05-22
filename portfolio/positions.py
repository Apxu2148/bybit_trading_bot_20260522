"""Future current-position reader.

Later stages will use this module to read current Bybit USDT perpetual futures
positions, normalize exchange-specific fields, and expose them to rebalance
planning code.

This module should not decide target exposure. It should only report current
portfolio state in a clean project-level format.
"""
