import asyncio
from collections.abc import Coroutine
from typing import Any

from ocr_rel.config import settings
from ocr_rel.logging_config import get_logger
from ocr_rel.tasks.queue import TaskExecutionQueue

logger = get_logger(__name__)


class BackgroundTaskRunner:
    def __init__(self) -> None:
        self._background_tasks: set[asyncio.Task[Any]] = set()
        self._queue = TaskExecutionQueue(settings.max_concurrent_tasks)

    def configure(self, max_concurrent: int | None = None) -> None:
        limit = max_concurrent if max_concurrent is not None else settings.max_concurrent_tasks
        self._queue.configure(limit)
        logger.info("Task execution queue configured maxConcurrent=%s", limit)

    def stats(self) -> dict[str, int]:
        return self._queue.stats()

    def run(self, coro: Coroutine[Any, Any, Any], *, task_id: str) -> None:
        async def wrapped() -> None:
            await self._queue.run(task_id, coro)

        task = asyncio.create_task(wrapped())
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        task.add_done_callback(self._log_task_error)

    @staticmethod
    def _log_task_error(task: asyncio.Task[Any]) -> None:
        if task.cancelled():
            return
        exc = task.exception()
        if exc:
            logger.exception("Background task failed: %s", exc)


background_runner = BackgroundTaskRunner()
