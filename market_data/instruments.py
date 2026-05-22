"""Future instrument discovery for Bybit USDT perpetual futures.

Later stages will use this module to load the list of tradable Bybit USDT
perpetual futures, cache instrument metadata, and refresh the universe on the
schedule configured by INSTRUMENTS_REFRESH_INTERVAL_HOURS.

The module should not contain strategy scoring or execution behavior. Its job
will be to describe what can be traded, not what should be traded.
"""
