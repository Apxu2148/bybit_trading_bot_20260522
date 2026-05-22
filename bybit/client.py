"""Future Bybit REST client wrapper.

This module will eventually own low-level communication with Bybit USDT
perpetual futures REST endpoints. It should be responsible for authentication,
request signing, response validation, rate-limit coordination, and clear error
messages.

Stage 1 intentionally does not implement real Bybit API calls. No function in
this project should connect to Bybit until the client contract is designed and
tested in a later stage.
"""
