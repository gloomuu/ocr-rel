from pathlib import Path

import aiosqlite

from ocr_rel.config import settings
from ocr_rel.logging_config import get_logger

logger = get_logger(__name__)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    registration_id TEXT,
    status TEXT NOT NULL,
    stage TEXT NOT NULL,
    progress INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    result_json TEXT,
    steps_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tasks_created_at ON tasks(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tasks_registration_id ON tasks(registration_id);
"""

MIGRATION_COLUMNS: list[tuple[str, str]] = [
    ("doc_type", "INTEGER"),
    ("doc_type_name", "TEXT"),
    ("file_size", "INTEGER"),
    ("file_format", "TEXT"),
    ("file_name", "TEXT"),
    ("duration_ms", "INTEGER"),
]


async def _migrate_schema(db: aiosqlite.Connection) -> None:
    cursor = await db.execute("PRAGMA table_info(tasks)")
    existing = {row[1] for row in await cursor.fetchall()}
    for column_name, column_type in MIGRATION_COLUMNS:
        if column_name not in existing:
            await db.execute(f"ALTER TABLE tasks ADD COLUMN {column_name} {column_type}")


async def init_db() -> None:
    db_path = Path(settings.database_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(db_path) as db:
        await db.executescript(SCHEMA_SQL)
        await _migrate_schema(db)
        await db.commit()
    logger.info("Database initialized at %s", db_path.resolve())
