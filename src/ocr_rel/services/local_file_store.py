from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime
from pathlib import Path

import aiosqlite

from ocr_rel.config import settings
from ocr_rel.logging_config import get_logger

logger = get_logger(__name__)

STORED_FILES_SCHEMA = """
CREATE TABLE IF NOT EXISTS stored_files (
    task_id TEXT PRIMARY KEY,
    file_name TEXT NOT NULL,
    rel_path TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_stored_files_created_at ON stored_files(created_at ASC);
"""


def _safe_filename(name: str) -> str:
    base = Path(name).name
    cleaned = re.sub(r"[^\w.\-()（）\u4e00-\u9fff]", "_", base).strip("._")
    return cleaned or "upload.bin"


def _guess_media_type(file_name: str) -> str:
    ext = Path(file_name).suffix.lower()
    mapping = {
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
    }
    return mapping.get(ext, "application/octet-stream")


class LocalFileStore:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._root = Path(settings.upload_storage_path)

    def _ensure_root(self) -> Path:
        self._root.mkdir(parents=True, exist_ok=True)
        return self._root

    async def init_db(self) -> None:
        async with aiosqlite.connect(Path(settings.database_path)) as db:
            await db.executescript(STORED_FILES_SCHEMA)
            await db.commit()

    async def save(self, task_id: str, *, file_name: str, content: bytes) -> str:
        safe_name = _safe_filename(file_name)
        rel_path = f"{task_id}_{safe_name}"
        absolute_path = self._ensure_root() / rel_path
        created_at = datetime.now(UTC).isoformat()

        async with self._lock:
            absolute_path.write_bytes(content)
            async with aiosqlite.connect(Path(settings.database_path)) as db:
                await db.execute(
                    """
                    INSERT INTO stored_files (task_id, file_name, rel_path, created_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(task_id) DO UPDATE SET
                        file_name=excluded.file_name,
                        rel_path=excluded.rel_path,
                        created_at=excluded.created_at
                    """,
                    (task_id, file_name, rel_path, created_at),
                )
                await db.commit()
            await self._enforce_retention_locked()
        logger.info("Stored upload file taskId=%s fileName=%s path=%s", task_id, file_name, rel_path)
        return rel_path

    async def get_file_path(self, task_id: str) -> tuple[Path, str] | None:
        async with aiosqlite.connect(Path(settings.database_path)) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT file_name, rel_path FROM stored_files WHERE task_id = ?",
                (task_id,),
            )
            row = await cursor.fetchone()
        if row is None:
            return None
        absolute_path = self._root / row["rel_path"]
        if not absolute_path.exists():
            return None
        return absolute_path, row["file_name"]

    async def has_file(self, task_id: str) -> bool:
        result = await self.get_file_path(task_id)
        return result is not None

    async def _enforce_retention_locked(self) -> None:
        max_files = settings.max_stored_files
        async with aiosqlite.connect(Path(settings.database_path)) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT task_id, rel_path FROM stored_files ORDER BY created_at ASC"
            )
            rows = await cursor.fetchall()

        overflow = len(rows) - max_files
        if overflow <= 0:
            return

        for row in rows[:overflow]:
            task_id = row["task_id"]
            rel_path = row["rel_path"]
            absolute_path = self._root / rel_path
            if absolute_path.exists():
                absolute_path.unlink()
            async with aiosqlite.connect(Path(settings.database_path)) as db:
                await db.execute("DELETE FROM stored_files WHERE task_id = ?", (task_id,))
                await db.commit()
            logger.info("Purged oldest stored file taskId=%s path=%s", task_id, rel_path)

    @staticmethod
    def media_type_for(file_name: str) -> str:
        return _guess_media_type(file_name)


local_file_store = LocalFileStore()
