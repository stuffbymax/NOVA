"""Logging setup for the application."""

import logging


def configure_logging(level: str = "INFO") -> None:
    """Configure a consistent console logger for NOVA."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
