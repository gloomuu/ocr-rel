from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any

from ocr_rel.logging_config import get_logger
from ocr_rel.services.task_manager import task_manager

logger = get_logger(__name__)


class TaskExecutionQueue:
    """Limits concurrent recognition tasks; excess tasks wait for a free slot."""

    def __init__(self, max_concurrent: int) -> None:
        self.configure(max_concurrent)
        self._waiting: list[str] = []
        self._running: set[str] = set()
        self._lock = asyncio.Lock()

    def configure(self, max_concurrent: int) -> None:
        if max_concurrent < 1:
            raise ValueError("max_concurrent must be >= 1")
        self._max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)

    @property
    def max_concurrent(self) -> int:
        return self._max_concurrent

    def stats(self) -> dict[str, int]:
        return {
            "maxConcurrent": self._max_concurrent,
            "running": len(self._running),
            "waiting": len(self._waiting),
            "available": max(self._max_concurrent - len(self._running), 0),
        }

    async def run(self, task_id: str, coro: Coroutine[Any, Any, Any]) -> None:
        await self._enter(task_id)
        try:
            await coro
        finally:
            await self._leave(task_id)

    async def _enter(self, task_id: str) -> None:
        queued = False
        async with self._lock:
            if len(self._running) >= self._max_concurrent:
                self._waiting.append(task_id)
                queue_position = len(self._waiting)
                queued = True

        if queued:
            logger.info(
                "Task queued taskId=%s position=%s running=%s waiting=%s",
                task_id,
                queue_position,
                len(self._running),
                len(self._waiting),
            )
            await task_manager.mark_queued(task_id, queue_position=queue_position)

        await self._semaphore.acquire()

        async with self._lock:
            if task_id in self._waiting:
                self._waiting.remove(task_id)
            self._running.add(task_id)

        if queued:
            logger.info("Task dequeued taskId=%s", task_id)

    async def _leave(self, task_id: str) -> None:
        async with self._lock:
            self._running.discard(task_id)
            waiting_snapshot = list(self._waiting)

        self._semaphore.release()

        for index, waiting_task_id in enumerate(waiting_snapshot, start=1):
            await task_manager.mark_queued(waiting_task_id, queue_position=index)
