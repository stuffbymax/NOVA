"""Image loading, scaling, and caching for the graphical presentation layer."""

from pathlib import Path

import pygame


class AssetError(RuntimeError):
    """Raised when a requested visual asset cannot be loaded."""


class AssetManager:
    """Loads each image once and provides consistently scaled copies."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self._cache: dict[Path, pygame.Surface] = {}
        self._scaled: dict[tuple[Path, tuple[int, int]], pygame.Surface] = {}

    def load(self, name: str) -> pygame.Surface:
        path = (self.root / name).resolve()
        if path not in self._cache:
            if not path.is_file():
                raise AssetError(f"Asset does not exist: {path}")
            try:
                self._cache[path] = pygame.image.load(path).convert_alpha()
            except pygame.error as error:
                raise AssetError(f"Could not load asset: {path}") from error
        return self._cache[path]

    def scaled(self, name: str, size: tuple[int, int]) -> pygame.Surface:
        key = ((self.root / name).resolve(), size)
        if key not in self._scaled:
            self._scaled[key] = pygame.transform.smoothscale(self.load(name), size)
        return self._scaled[key]

    def clear(self) -> None:
        self._cache.clear()
        self._scaled.clear()
