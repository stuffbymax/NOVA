"""Deterministic random number generation for reproducible simulations."""

import random
from typing import TypeVar


T = TypeVar("T")


class DeterministicRng:
    """Owns an isolated random stream so generation can be replayed by seed."""

    def __init__(self, seed: int | str) -> None:
        self._random = random.Random(seed)

    def random(self) -> float:
        return self._random.random()

    def randint(self, start: int, stop: int) -> int:
        return self._random.randint(start, stop)

    def choice(self, values: list[T] | tuple[T, ...]) -> T:
        if not values:
            raise ValueError("Cannot choose from an empty collection")
        return self._random.choice(values)
