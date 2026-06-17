from fastapi import HTTPException, status

from ocr_rel.config import settings


def validate_upload_size(content: bytes, *, filename: str | None = None) -> None:
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file")
    max_size = settings.max_upload_file_size
    if len(content) > max_size:
        limit_mb = max_size / (1024 * 1024)
        name = filename or "file"
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File {name} exceeds upload limit ({limit_mb:.0f}MB)",
        )
