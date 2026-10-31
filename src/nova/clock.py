"""Deterministic simulation clock and scheduled callbacks."""

from dataclasses import dataclass, field
import heapq
from typing import Callable


ScheduledCallback = Callable[[], None]


@dataclass(order=True)
class _ScheduledEvent:
    due_at: float
    sequence: int
    callback: ScheduledCallback = field(compare=False)


class GameClock:
    """Tracks simulation time independently from rendering time."""

    def __init__(self) -> None:
        self.time = 0.0
        self.speed = 1.0
        self.paused = True
        self._sequence = 0
        self._scheduled: list[_ScheduledEvent] = []

    def resume(self) -> None:
        self.paused = False

    def pause(self) -> None:
        self.paused = True

    def set_speed(self, speed: float) -> None:
        if speed < 0:
            raise ValueError("Simulation speed cannot be negative")
        self.speed = speed

    def schedule(self, delay: float, callback: ScheduledCallback) -> None:
        if delay < 0:
            raise ValueError("Scheduled delay cannot be negative")
        self._sequence += 1
        heapq.heappush(
            self._scheduled,
            _ScheduledEvent(self.time + delay, self._sequence, callback),
        )

    def advance(self, real_delta: float) -> float:
        """Advance simulation time and run callbacks that become due."""
        if real_delta < 0:
            raise ValueError("Delta time cannot be negative")
        if self.paused or self.speed == 0:
            return 0.0
        simulation_delta = real_delta * self.speed
        self.time += simulation_delta
        while self._scheduled and self._scheduled[0].due_at <= self.time:
            heapq.heappop(self._scheduled).callback()
        return simulation_delta
