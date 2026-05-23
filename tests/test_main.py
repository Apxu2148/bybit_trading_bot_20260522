from __future__ import annotations

import main as main_module
from pytest import MonkeyPatch


def test_main_calls_run_bot_loop(monkeypatch: MonkeyPatch) -> None:
    calls = {"count": 0}

    def fake_run_bot_loop() -> None:
        calls["count"] += 1

    monkeypatch.setattr(main_module, "run_bot_loop", fake_run_bot_loop)

    main_module.main()

    assert calls["count"] == 1
