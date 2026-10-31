"""Worker-thread task management with main-thread result delivery."""

from concurrent.futures import Future, ThreadPoolExecutor
from collections.abc import Callable
import logging
from queue import Empty, SimpleQueue
from typing import TypeVar


logger = logging.getLogger(__name__)
T = TypeVar("T")


class BackgroundTaskManager:
    """Runs blocking work off-thread and delivers its result during update."""

    def __init__(self, max_workers: int = 2) -> None:
        if max_workers < 1:
            raise ValueError("At least one background worker is required")
        self.max_workers = max_workers
        self._executor: ThreadPoolExecutor | None = None
        self._completions: SimpleQueue[Callable[[], None]] = SimpleQueue()

    @property
    def running(self) -> bool:
        return self._executor is not None

    def start(self) -> None:
        """Create the worker pool, if it is not already running."""
        if self._executor is None:
            self._executor = ThreadPoolExecutor(
                max_workers=self.max_workers,
                thread_name_prefix="nova-worker",
            )

    def submit(
        self,
        function: Callable[..., T],
        *args: object,
        on_complete: Callable[[T], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
        **kwargs: object,
    ) -> Future[T]:
        """Schedule work and queue its callbacks for the next update."""
        if self._executor is None:
            raise RuntimeError("Background task manager has not been started")
        future = self._executor.submit(function, *args, **kwargs)

        def enqueue_completion(completed: Future[T]) -> None:
            def deliver() -> None:
                try:
                    result = completed.result()
                except Exception as error:
                    logger.exception("Background task failed")
                    if on_error is not None:
                        on_error(error)
                else:
                    if on_complete is not None:
                        on_complete(result)

            self._completions.put(deliver)

        future.add_done_callback(enqueue_completion)
        return future

    def update(self) -> int:
        """Deliver completed-task callbacks on the calling thread."""
        delivered = 0
        while True:
            try:
                callback = self._completions.get_nowait()
            except Empty:
                break
            callback()
            delivered += 1
        return delivered

    def shutdown(self, wait: bool = True) -> None:
        """Stop accepting tasks and optionally wait for running work."""
        executor, self._executor = self._executor, None
        if executor is not None:
            executor.shutdown(wait=wait, cancel_futures=True)
        if wait:
            self.update()
