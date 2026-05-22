"""Future MA-based limit-order rebalancer.

Later stages will execute planned delta quantities through limit orders. The
intended execution flow is to calculate a moving-average reference price, place
or adjust passive limit orders, and periodically check whether the rebalance is
complete.

The maximum-duration configuration is present but disabled in Stage 1. No
execution logic or Bybit API calls are implemented here yet.
"""
