"""Reusable logger setup for the Bybit trading bot.

Stage 2 still only needs infrastructure logging. The setup below prepares three
separate loggers so future modules can keep operational messages separated:

* main: high-level lifecycle messages.
* execution: future order and rebalance execution messages.
* filtering: future instrument filtering and exclusion reasons.

The function is deliberately idempotent. It can be called by tests, scripts, or
future workers more than once without stacking duplicate handlers on a logger.

Security note:
    Log messages must never include API keys, API secrets, request signatures, or
    full request headers. Future Bybit client code should sanitize values before
    passing them to any logger. This module cannot know which values are secret,
    so the rule is documented here and must be enforced at call sites too.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from config import config

LOGGER_FILES = {
    "main": "main.log",
    "execution": "execution.log",
    "filtering": "filtering.log",
}

LOGGER_NAMES = {
    "main": "main",
    "execution": "execution",
    "filtering": "filtering",
}


def setup_loggers() -> dict[str, logging.Logger]:
    """Create and return the project loggers.

    Returns:
        A dictionary with "main", "execution", and "filtering" logger keys.

    The returned dictionary always has exactly these keys: "main", "execution",
    and "filtering". The function removes only handlers that were previously
    created by this setup function. User-added handlers are left untouched,
    which keeps the logger friendly to tests and future integrations.
    """
    log_dir = Path(config.LOG_DIR)
    log_dir.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    loggers: dict[str, logging.Logger] = {}
    for key, file_name in LOGGER_FILES.items():
        logger = logging.getLogger(LOGGER_NAMES[key])
        logger.setLevel(logging.INFO)
        logger.propagate = False

        _remove_managed_handlers(logger)

        file_handler = _build_file_handler(log_dir / file_name)
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)
        _mark_managed(file_handler)
        logger.addHandler(file_handler)

        stdout_handler = logging.StreamHandler(sys.stdout)
        stdout_handler.setLevel(logging.INFO)
        stdout_handler.setFormatter(formatter)
        _mark_managed(stdout_handler)
        logger.addHandler(stdout_handler)

        loggers[key] = logger

    return loggers


def get_loggers() -> dict[str, logging.Logger]:
    """Return configured project loggers, creating handlers if needed."""
    if _all_managed_loggers_ready():
        return {key: logging.getLogger(LOGGER_NAMES[key]) for key in LOGGER_NAMES}
    return setup_loggers()


def get_main_logger() -> logging.Logger:
    """Return the configured main logger."""
    return get_loggers()["main"]


def _build_file_handler(path: Path) -> logging.Handler:
    """Build either a rotating or a plain file handler based on config."""
    if config.LOG_ROTATION_ENABLED == 1:
        return RotatingFileHandler(
            filename=path,
            maxBytes=config.LOG_MAX_BYTES,
            backupCount=config.LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
    return logging.FileHandler(filename=path, encoding="utf-8")


def _remove_managed_handlers(logger: logging.Logger) -> None:
    """Remove handlers that were created by setup_loggers()."""
    for handler in list(logger.handlers):
        if getattr(handler, "_bybit_bot_managed", False):
            logger.removeHandler(handler)
            handler.close()


def _mark_managed(handler: logging.Handler) -> None:
    """Mark a handler so future setup calls can remove it safely."""
    setattr(handler, "_bybit_bot_managed", True)


def _all_managed_loggers_ready() -> bool:
    """Check whether all project loggers already have managed handlers."""
    for logger_name in LOGGER_NAMES.values():
        logger = logging.getLogger(logger_name)
        managed_handlers = [
            handler for handler in logger.handlers if getattr(handler, "_bybit_bot_managed", False)
        ]
        if len(managed_handlers) != 2:
            return False
    return True
