"""Scene lifecycle and scene switching."""

from typing import Protocol

from .state import GameState


class Scene(Protocol):
    def update(self, delta: float, state: GameState) -> None: ...


class SceneManager:
    """Keeps exactly one active scene while allowing future UI scenes."""

    def __init__(self) -> None:
        self._active: Scene | None = None

    @property
    def active(self) -> Scene | None:
        return self._active

    def switch_to(self, scene: Scene | None) -> None:
        self._active = scene

    def update(self, delta: float, state: GameState) -> None:
        if self._active is not None:
            self._active.update(delta, state)
