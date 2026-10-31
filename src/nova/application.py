"""Application lifecycle."""

import logging

from .config import Config

logger = logging.getLogger(__name__)


class Application:
    """Minimal application shell until the game loop is introduced."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self._running = False

    def start(self) -> None:
        """Start the application and perform initial setup."""
        self._running = True
        logger.info("NOVA started")
        if self.config.debug:
            logger.debug("Debug mode enabled")

    def shutdown(self) -> None:
        """Stop the application and release resources."""
        if self._running:
            logger.info("NOVA shutting down")
            self._running = False
