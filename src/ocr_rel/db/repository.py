from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import aiosqlite

from ocr_rel.config import settings
from ocr_rel.models.schemas import CallbackPayload, TaskRecord, TaskStatus, TaskStep, TaskSummary


def _serialize_steps(steps: list[TaskStep]) -> str:
    return json.dumps([step.model_dump() for step in steps], ensure_ascii=False)


def _deserialize_steps(raw: str | None) -> list[TaskStep]:
    if not raw:
        return []
    data = json.loads(raw)
    return [TaskStep.model_validate(item) for item in data]


def _deserialize_result(raw: str | None) -> CallbackPayload | None:
    if not raw:
        return None
    return CallbackPayload.model_validate(json.loads(raw))


def _row_to_record(row) -> TaskRecord:
    return TaskRecord(
        task_id=row["task_id"],
        status=TaskStatus(row["status"]),
        registration_id=row["registration_id"],
        stage=row["stage"],
        progress=row["progress"],
        steps=_deserialize_steps(row["steps_json"]),
        error=row["error"],
        result=_deserialize_result(row["result_json"]),
        doc_type=row["doc_type"],
        doc_type_name=row["doc_type_name"],
        file_size=row["file_size"],
        file_format=row["file_format"] if "file_format" in row.keys() else None,
        file_name=row["file_name"] if "file_name" in row.keys() else None,
        has_stored_file=bool(row["has_stored_file"]) if "has_stored_file" in row.keys() else False,
        duration_ms=row["duration_ms"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


class TaskRepository:
    async def save(self, record: TaskRecord) -> None:
        result_json = (
            json.dumps(record.result.model_dump(), ensure_ascii=False) if record.result else None
        )
        async with aiosqlite.connect(Path(settings.database_path)) as db:
            db.row_factory = aiosqlite.Row
            await db.execute(
                """
                INSERT INTO tasks (
                    task_id, registration_id, status, stage, progress,
                    error, result_json, steps_json,
                    doc_type, doc_type_name, file_size, file_format, file_name, duration_ms,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    registration_id=excluded.registration_id,
                    status=excluded.status,
                    stage=excluded.stage,
                    progress=excluded.progress,
                    error=excluded.error,
                    result_json=excluded.result_json,
                    steps_json=excluded.steps_json,
                    doc_type=excluded.doc_type,
                    doc_type_name=excluded.doc_type_name,
                    file_size=excluded.file_size,
                    file_format=excluded.file_format,
                    file_name=excluded.file_name,
                    duration_ms=excluded.duration_ms,
                    updated_at=excluded.updated_at
                """,
                (
                    record.task_id,
                    record.registration_id,
                    record.status.value,
                    record.stage,
                    record.progress,
                    record.error,
                    result_json,
                    _serialize_steps(record.steps),
                    record.doc_type,
                    record.doc_type_name,
                    record.file_size,
                    record.file_format,
                    record.file_name,
                    record.duration_ms,
                    record.created_at.isoformat(),
                    record.updated_at.isoformat(),
                ),
            )
            await db.commit()

    async def get(self, task_id: str) -> TaskRecord | None:
        async with aiosqlite.connect(Path(settings.database_path)) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT t.*,
                       CASE WHEN sf.task_id IS NOT NULL THEN 1 ELSE 0 END AS has_stored_file
                FROM tasks t
                LEFT JOIN stored_files sf ON sf.task_id = t.task_id
                WHERE t.task_id = ?
                """,
                (task_id,),
            )
            row = await cursor.fetchone()
        if row is None:
            return None
        return _row_to_record(row)

    async def list_tasks(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        registration_id: str | None = None,
    ) -> tuple[list[TaskSummary], int]:
        offset = (page - 1) * page_size
        where_clause = ""
        params: list[object] = []
        if registration_id:
            where_clause = "WHERE registration_id = ?"
            params.append(registration_id)

        async with aiosqlite.connect(Path(settings.database_path)) as db:
            db.row_factory = aiosqlite.Row
            count_cursor = await db.execute(
                f"SELECT COUNT(*) AS total FROM tasks {where_clause}",
                params,
            )
            count_row = await count_cursor.fetchone()
            total = int(count_row["total"])

            cursor = await db.execute(
                f"""
                SELECT t.task_id, t.registration_id, t.status, t.stage, t.progress,
                       t.result_json, t.doc_type, t.doc_type_name, t.file_size, t.file_format,
                       t.file_name, t.duration_ms, t.created_at, t.updated_at,
                       CASE WHEN sf.task_id IS NOT NULL THEN 1 ELSE 0 END AS has_stored_file
                FROM tasks t
                LEFT JOIN stored_files sf ON sf.task_id = t.task_id
                {where_clause.replace("registration_id", "t.registration_id")}
                ORDER BY t.created_at DESC
                LIMIT ? OFFSET ?
                """,
                [*params, page_size, offset],
            )
            rows = await cursor.fetchall()

        summaries = [
            TaskSummary(
                taskId=row["task_id"],
                registrationId=row["registration_id"],
                status=TaskStatus(row["status"]),
                stage=row["stage"],
                progress=row["progress"],
                hasResult=bool(row["result_json"]),
                docType=row["doc_type"],
                docTypeName=row["doc_type_name"],
                fileFormat=row["file_format"] if "file_format" in row.keys() else None,
                fileName=row["file_name"],
                hasStoredFile=bool(row["has_stored_file"]),
                fileSize=row["file_size"],
                durationMs=row["duration_ms"],
                createdAt=row["created_at"],
                updatedAt=row["updated_at"],
            )
            for row in rows
        ]
        return summaries, total


task_repository = TaskRepository()
