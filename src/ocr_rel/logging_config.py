import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from ocr_rel.config import settings

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s - %(message)s"


def setup_logging() -> None:
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(level)

    if root.handlers:
        root.handlers.clear()

    formatter = logging.Formatter(LOG_FORMAT)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root.addHandler(console_handler)

    if settings.log_file_enabled:
        log_dir = Path(settings.log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / settings.log_file_name
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=settings.log_max_bytes,
            backupCount=settings.log_backup_count,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
        logging.getLogger(__name__).info("File logging enabled: %s", log_path.resolve())


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def log_step(
    logger: logging.Logger,
    *,
    task_id: str | None = None,
    registration_id: str | None = None,
    step: str,
    message: str,
    **extra: Any,
) -> None:
    parts = [f"step={step}", message]
    if task_id:
        parts.insert(0, f"taskId={task_id}")
    if registration_id:
        parts.insert(1 if task_id else 0, f"registrationId={registration_id}")
    if extra:
        parts.append(f"extra={json.dumps(extra, ensure_ascii=False, default=str)}")
    logger.info(" | ".join(parts))


def log_ocr_text(
    logger: logging.Logger,
    *,
    task_id: str | None = None,
    registration_id: str | None = None,
    doc_type: int | None = None,
    text: str,
    step: str = "ocr.text",
) -> None:
    """Log full OCR text on separate lines for debugging."""
    parts: list[str] = []
    if task_id:
        parts.append(f"taskId={task_id}")
    if registration_id:
        parts.append(f"registrationId={registration_id}")
    parts.append(f"step={step}")
    parts.append("OCR识别内容")
    if doc_type is not None:
        parts.append(f"docType={doc_type}")
    parts.append(f"textLength={len(text)}")
    header = " | ".join(parts)
    logger.info("%s\n%s", header, text)


def log_result(
    logger: logging.Logger,
    *,
    task_id: str,
    registration_id: str | None,
    result: dict[str, Any],
) -> None:
    logger.info(
        "taskId=%s | registrationId=%s | step=result | payload=%s",
        task_id,
        registration_id or "",
        json.dumps(result, ensure_ascii=False, default=str),
    )
