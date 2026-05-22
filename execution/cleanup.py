"""Future cleanup for small leftover positions.

Later stages will detect small leftover positions, try to close them by market
order up to SMALL_POSITION_CLEANUP_MAX_MARKET_ATTEMPTS times, then try market
reduce-only orders up to SMALL_POSITION_CLEANUP_MAX_REDUCE_ONLY_ATTEMPTS times
if normal cleanup fails.

If cleanup still fails, the future implementation should leave the position and
log a clear error. Stage 1 does not implement execution logic.
"""
