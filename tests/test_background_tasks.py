import threading
import time

import pytest

from nova.background_tasks import BackgroundTaskManager


def test_background_result_callback_runs_on_update_thread() -> None:
    manager = BackgroundTaskManager(max_workers=1)
    completed: list[tuple[object, int]] = []
    callback_thread: list[int] = []
    manager.start()

    def record_result(result: object) -> None:
        completed.append((result, threading.get_ident()))
        callback_thread.append(threading.get_ident())

    try:
        future = manager.submit(
            lambda value: value + 1,
            4,
            on_complete=record_result,
        )
        assert future.result(timeout=2) == 5
        deadline = time.monotonic() + 2
        while not completed and time.monotonic() < deadline:
            manager.update()
            time.sleep(0.001)

        assert completed == [(5, threading.get_ident())]
        assert callback_thread == [threading.get_ident()]
    finally:
        manager.shutdown()


def test_background_task_errors_are_reported_on_update() -> None:
    manager = BackgroundTaskManager(max_workers=1)
    errors: list[str] = []
    manager.start()

    try:
        future = manager.submit(
            lambda: 1 / 0,
            on_error=lambda error: errors.append(str(error)),
        )
        with pytest.raises(ZeroDivisionError):
            future.result(timeout=2)

        deadline = time.monotonic() + 2
        while not errors and time.monotonic() < deadline:
            manager.update()
            time.sleep(0.001)

        assert errors == ["division by zero"]
    finally:
        manager.shutdown()
