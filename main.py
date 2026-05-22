from __future__ import annotations

from logging_setup.logger import setup_loggers
from state.state_manager import load_state


def main() -> None:
    """Initialize Stage 2 infrastructure without connecting to any exchange."""
    loggers = setup_loggers()
    state = load_state()

    loggers["main"].info("Stage 2 infrastructure check is ready.")
    loggers["main"].info("Loaded runtime state keys: %s", sorted(state.keys()))
    print("Stage 2 infrastructure check is ready.")


if __name__ == "__main__":
    main()
