import asyncio
import uuid
from datetime import UTC, datetime

from ocr_rel.db.repository import task_repository
from ocr_rel.models.schemas import (
    CallbackPayload,
    TaskRecord,
    TaskStage,
    TaskStatus,
    TaskStep,
    TaskSummary,
)


class TaskManager:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()

    async def _persist(self, record: TaskRecord) -> None:
        await task_repository.save(record)

    @staticmethod
    def _set_duration(record: TaskRecord) -> None:
        if record.created_at is None or record.updated_at is None:
            return
        record.duration_ms = int((record.updated_at - record.created_at).total_seconds() * 1000)

    async def create_task(
        self,
        registration_id: str | None = None,
        *,
        doc_type: int | None = None,
        doc_type_name: str | None = None,
        file_size: int | None = None,
        file_format: str | None = None,
        file_name: str | None = None,
    ) -> TaskRecord:
        now = datetime.now(UTC)
        task_id = str(uuid.uuid4())
        record = TaskRecord(
            task_id=task_id,
            status=TaskStatus.PENDING,
            registration_id=registration_id,
            stage=TaskStage.ACCEPTED,
            progress=5,
            doc_type=doc_type,
            doc_type_name=doc_type_name,
            file_size=file_size,
            file_format=file_format,
            file_name=file_name,
            steps=[
                TaskStep(
                    stage=TaskStage.ACCEPTED,
                    message="识别请求已受理",
                    progress=5,
                    at=now.isoformat(),
                )
            ],
            created_at=now,
            updated_at=now,
        )
        async with self._lock:
            await self._persist(record)
        return record

    async def get_task(self, task_id: str) -> TaskRecord | None:
        return await task_repository.get(task_id)

    async def list_tasks(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        registration_id: str | None = None,
    ) -> tuple[list[TaskSummary], int]:
        return await task_repository.list_tasks(
            page=page,
            page_size=page_size,
            registration_id=registration_id,
        )

    async def update_progress(
        self,
        task_id: str,
        *,
        stage: str,
        progress: int,
        message: str,
        status: TaskStatus | None = None,
    ) -> None:
        async with self._lock:
            record = await task_repository.get(task_id)
            if record is None:
                raise KeyError(f"Task not found: {task_id}")
            record.stage = stage
            record.progress = progress
            record.updated_at = datetime.now(UTC)
            if status is not None:
                record.status = status
            record.steps.append(
                TaskStep(
                    stage=stage,
                    message=message,
                    progress=progress,
                    at=record.updated_at.isoformat(),
                )
            )
            await self._persist(record)

    async def update_file_metadata(
        self,
        task_id: str,
        *,
        doc_type: int | None = None,
        doc_type_name: str | None = None,
        file_size: int | None = None,
        file_format: str | None = None,
        file_name: str | None = None,
    ) -> None:
        async with self._lock:
            record = await task_repository.get(task_id)
            if record is None:
                raise KeyError(f"Task not found: {task_id}")
            if doc_type is not None:
                record.doc_type = doc_type
            if doc_type_name is not None:
                record.doc_type_name = doc_type_name
            if file_size is not None:
                record.file_size = file_size
            if file_format is not None:
                record.file_format = file_format
            if file_name is not None:
                record.file_name = file_name
            record.updated_at = datetime.now(UTC)
            await self._persist(record)

    async def mark_queued(self, task_id: str, *, queue_position: int) -> None:
        ahead = max(queue_position - 1, 0)
        if ahead == 0:
            message = "排队等待空闲执行槽位"
        else:
            message = f"排队等待中，前方还有 {ahead} 个任务"
        await self.update_progress(
            task_id,
            stage=TaskStage.QUEUED,
            progress=5,
            message=message,
            status=TaskStatus.PENDING,
        )

    async def mark_running(self, task_id: str) -> None:
        await self.update_progress(
            task_id,
            stage=TaskStage.DOWNLOADING,
            progress=10,
            message="开始处理识别任务",
            status=TaskStatus.RUNNING,
        )

    async def mark_success(self, task_id: str, result: CallbackPayload) -> None:
        async with self._lock:
            record = await task_repository.get(task_id)
            if record is None:
                raise KeyError(f"Task not found: {task_id}")
            record.status = TaskStatus.SUCCESS
            record.stage = TaskStage.COMPLETED
            record.progress = 100
            record.result = result
            record.updated_at = datetime.now(UTC)
            self._set_duration(record)
            record.steps.append(
                TaskStep(
                    stage=TaskStage.COMPLETED,
                    message="识别完成，结果已就绪",
                    progress=100,
                    at=record.updated_at.isoformat(),
                )
            )
            await self._persist(record)

    async def mark_failed(self, task_id: str, error: str) -> None:
        async with self._lock:
            record = await task_repository.get(task_id)
            if record is None:
                raise KeyError(f"Task not found: {task_id}")
            record.status = TaskStatus.FAILED
            record.stage = TaskStage.FAILED
            record.error = error
            record.updated_at = datetime.now(UTC)
            self._set_duration(record)
            record.steps.append(
                TaskStep(
                    stage=TaskStage.FAILED,
                    message=error,
                    progress=record.progress,
                    at=record.updated_at.isoformat(),
                )
            )
            await self._persist(record)


task_manager = TaskManager()
