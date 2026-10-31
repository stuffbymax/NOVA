"""Core simulation engine, independent of pygame and user interface code."""

from .background_tasks import BackgroundTaskManager
from .clock import GameClock
from .entities import EntityManager
from .events import EventBus
from .rng import DeterministicRng
from .scenes import SceneManager
from .state import GameState
from .ticks import TickScheduler


class GameEngine:
    """Coordinates simulation time, state, entities, events, and scenes."""

    def __init__(self) -> None:
        self.clock = GameClock()
        self.state = GameState()
        self.entities = EntityManager()
        self.events = EventBus()
        self.scenes = SceneManager()
        self.ticks = TickScheduler()
        self.rng = DeterministicRng(0)
        self.background_tasks = BackgroundTaskManager()
        self._started = False

    @property
    def started(self) -> bool:
        return self._started

    def start(self) -> None:
        self.background_tasks.start()
        self._started = True
        self.clock.resume()

    def stop(self) -> None:
        self.clock.pause()
        self._started = False
        self.background_tasks.shutdown()

    def update(self, real_delta: float) -> float:
        """Advance simulation and return the simulated delta."""
        if real_delta < 0:
            raise ValueError("Delta time cannot be negative")
        if not self._started:
            return 0.0
        self.background_tasks.update()
        simulated_delta = self.clock.advance(real_delta)
        self.scenes.update(simulated_delta, self.state)
        self.ticks.advance(simulated_delta)
        self.events.publish("simulation.updated", simulated_delta)
        return simulated_delta
