"""Serializable game state container."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class GameState:
    """Mutable state owned by the simulation, separate from rendering."""

    values: dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self.values.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.values[key] = value
