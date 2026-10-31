"""NOVA command-line entry point."""

import argparse
import logging
from pathlib import Path

from .application import Application
from .config import Config, load_config
from .logging_config import configure_logging

logger = logging.getLogger(__name__)


def main() -> int:
    """Run NOVA and return a process exit code."""
    parser = argparse.ArgumentParser(description="Start NOVA.")
    parser.add_argument("--config", type=str, help="Path to a TOML config file.")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging.")
    args = parser.parse_args()

    config = load_config(Path(args.config)) if args.config else load_config()
    if args.debug:
        config = Config(debug=True, log_level="DEBUG")
    configure_logging(config.log_level)

    application = Application(config)
    try:
        application.start()
    except Exception:
        logger.exception("NOVA failed to start")
        return 1
    finally:
        application.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
