"""Application lifecycle."""

import logging

from .config import Config
from .content import ContentCatalog, FactionDefinition, NationDefinition
from .engine import GameEngine

logger = logging.getLogger(__name__)


class Application:
    """Application lifecycle around the UI-independent game engine."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.engine = GameEngine()
        self.content = ContentCatalog(config.content_path)
        self.factions: dict[str, FactionDefinition] = self.content.factions
        self.nations: dict[str, NationDefinition] = self.content.nations
        self._running = False

    def start(self) -> None:
        """Start the application and perform initial setup."""
        self._running = True
        self.engine.start()
        logger.info("NOVA started")
        if self.config.debug:
            logger.debug("Debug mode enabled")

    def shutdown(self) -> None:
        """Stop the application and release resources."""
        if self._running:
            logger.info("NOVA shutting down")
            self.engine.stop()
            self._running = False

    def update(self, real_delta: float) -> float:
        """Advance the game simulation from a future rendering loop."""
        if not self._running:
            return 0.0
        return self.engine.update(real_delta)
