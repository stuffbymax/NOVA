"""Fixed-interval simulation tick scheduling."""

from collections.abc import Callable


TickCallback = Callable[[float], None]


class TickScheduler:
    """Runs callbacks at a fixed simulation interval without losing elapsed time."""

    def __init__(self, interval: float = 1.0) -> None:
        if interval <= 0:
            raise ValueError("Tick interval must be greater than zero")
        self.interval = interval
        self._accumulator = 0.0
        self._callbacks: list[TickCallback] = []

    def add(self, callback: TickCallback) -> None:
        if callback not in self._callbacks:
            self._callbacks.append(callback)

    def remove(self, callback: TickCallback) -> None:
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def advance(self, delta: float) -> int:
        """Consume simulated time and return the number of ticks emitted."""
        if delta < 0:
            raise ValueError("Tick delta cannot be negative")
        self._accumulator += delta
        tick_count = 0
        while self._accumulator >= self.interval:
            self._accumulator -= self.interval
            tick_count += 1
            for callback in tuple(self._callbacks):
                callback(self.interval)
        return tick_count
