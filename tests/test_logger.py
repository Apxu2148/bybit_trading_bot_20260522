from __future__ import annotations

import logging
from pathlib import Path

from pytest import MonkeyPatch

from config import config
from logging_setup.logger import setup_loggers


def test_setup_loggers_returns_expected_loggers(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(config, "LOG_DIR", str(tmp_path))

    loggers = setup_loggers()

    assert set(loggers) == {"main", "execution", "filtering"}
    assert all(isinstance(logger, logging.Logger) for logger in loggers.values())
    assert (tmp_path / "main.log").exists()
    assert (tmp_path / "execution.log").exists()
    assert (tmp_path / "filtering.log").exists()


def test_setup_loggers_does_not_duplicate_handlers(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(config, "LOG_DIR", str(tmp_path))

    first_loggers = setup_loggers()
    first_counts = {name: len(logger.handlers) for name, logger in first_loggers.items()}

    second_loggers = setup_loggers()
    second_counts = {name: len(logger.handlers) for name, logger in second_loggers.items()}

    assert first_counts == second_counts
    assert all(count == 2 for count in second_counts.values())


def test_loggers_write_messages_to_expected_files(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(config, "LOG_DIR", str(tmp_path))

    loggers = setup_loggers()
    loggers["main"].info("main test message")
    loggers["execution"].info("execution test message")
    loggers["filtering"].info("filtering test message")

    for logger in loggers.values():
        for handler in logger.handlers:
            handler.flush()

    assert "main test message" in (tmp_path / "main.log").read_text(encoding="utf-8")
    assert "execution test message" in (tmp_path / "execution.log").read_text(encoding="utf-8")
    assert "filtering test message" in (tmp_path / "filtering.log").read_text(encoding="utf-8")
