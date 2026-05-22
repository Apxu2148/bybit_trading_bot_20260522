"""Future leverage setup before rebalance execution.

Later stages will try to enable cross margin if possible, then try leverage
candidates from LEVERAGE_CANDIDATES in order. The first leverage accepted by
Bybit should be used before rebalance execution starts.

Stage 1 intentionally does not connect to Bybit and does not change leverage.
"""
