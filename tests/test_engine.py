from nova.engine import GameEngine
from nova.application import Application
from nova.config import Config
from nova.rng import DeterministicRng
from nova.ticks import TickScheduler


def test_engine_advances_clock_and_scene() -> None:
    engine = GameEngine()
    updates: list[float] = []
    engine.events.subscribe("simulation.updated", updates.append)
    engine.start()

    assert engine.update(2.0) == 2.0
    assert engine.clock.time == 2.0
    assert updates == [2.0]


def test_paused_clock_does_not_advance() -> None:
    engine = GameEngine()
    engine.start()
    engine.clock.pause()

    assert engine.update(1.0) == 0.0
    assert engine.clock.time == 0.0


def test_scheduled_event_runs_when_due() -> None:
    engine = GameEngine()
    called: list[bool] = []
    engine.clock.schedule(1.0, lambda: called.append(True))
    engine.start()

    engine.update(0.5)
    assert called == []
    engine.update(0.5)
    assert called == [True]


def test_tick_scheduler_emits_fixed_ticks() -> None:
    scheduler = TickScheduler(interval=0.5)
    ticks: list[float] = []
    scheduler.add(ticks.append)

    assert scheduler.advance(1.2) == 2
    assert ticks == [0.5, 0.5]
    assert scheduler.advance(0.3) == 1


def test_deterministic_rng_replays_same_sequence() -> None:
    first = DeterministicRng("galaxy-seed")
    second = DeterministicRng("galaxy-seed")

    assert [first.random() for _ in range(3)] == [second.random() for _ in range(3)]


def test_engine_rejects_negative_delta() -> None:
    engine = GameEngine()

    try:
        engine.update(-1.0)
    except ValueError as error:
        assert str(error) == "Delta time cannot be negative"
    else:
        raise AssertionError("Expected negative delta to be rejected")


def test_application_campaign_advances_with_unpaused_simulation(tmp_path) -> None:
    application = Application(Config(content_path=tmp_path))
    application.start()
    application.engine.clock.pause()

    assert application.update(5) == 0
    assert application.campaign.elapsed_days == 0

    application.engine.clock.resume()
    assert application.update(5) == 5
    assert application.campaign.elapsed_days == 5
    application.shutdown()
