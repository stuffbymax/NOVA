"""Application lifecycle."""

import logging
from pathlib import Path

from .campaign import Campaign
from .config import Config
from .content import ContentCatalog, FactionDefinition, NationDefinition
from .engine import GameEngine
from .persistence import load_campaign, save_campaign

logger = logging.getLogger(__name__)


class Application:
    """Application lifecycle around the UI-independent game engine."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.engine = GameEngine()
        self.campaign = Campaign(
            seed=config.galaxy_seed,
            size=config.galaxy_size,
            shape=config.galaxy_shape,
            galaxy_name=config.galaxy_name,
            content_path=config.content_path,
        )
        self.content = ContentCatalog(config.content_path)
        self.factions: dict[str, FactionDefinition] = self.content.factions
        self.nations: dict[str, NationDefinition] = self.content.nations
        self._running = False

    @property
    def quick_save_path(self) -> Path:
        return self.config.save_path / "quick-save.json"

    def new_game(
        self,
        player_species_id: str = "union-human",
        name_culture: str = "all",
    ) -> None:
        self.campaign = Campaign(
            seed=self.config.galaxy_seed,
            size=self.config.galaxy_size,
            shape=self.config.galaxy_shape,
            galaxy_name=self.config.galaxy_name,
            player_species_id=player_species_id,
            name_culture=name_culture,
            content_path=self.config.content_path,
        )

    def save_game(self, path: Path | None = None) -> None:
        save_campaign(path or self.quick_save_path, self.campaign)

    def load_game(self, path: Path | None = None) -> None:
        self.campaign = load_campaign(
            path or self.quick_save_path,
            self.config.content_path,
        )

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
        simulated_delta = self.engine.update(real_delta)
        self.campaign.advance(simulated_delta)
        return simulated_delta
