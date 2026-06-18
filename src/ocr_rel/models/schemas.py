from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

ATTACHMENT_TYPE_NAMES: dict[int, str] = {
    1: "营业执照",
    2: "法人身份证",
    3: "审计报告",
    4: "验资报告",
    5: "从业人员身份证",
    6: "等级保护备案/软件著作权",
    7: "法人征信报告",
    8: "信用证明",
    9: "信用证明",
    10: "信用证明",
    11: "信用证明",
}


class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class TaskStage(StrEnum):
    ACCEPTED = "accepted"
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    OCR = "ocr"
    EXTRACTING = "extracting"
    CALLBACK = "callback"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskStep(BaseModel):
    stage: str
    message: str
    progress: int
    at: str


class FileRef(BaseModel):
    uuid: str
    personnel: str | None = None


class FileTypeGroup(BaseModel):
    type: int = Field(ge=1, le=11)
    name: str
    files: list[FileRef]


class RecognizeRequest(BaseModel):
    registrationId: str
    files: list[FileTypeGroup]


class RecognizeResponse(BaseModel):
    taskId: str


class ApiResponse(BaseModel):
    code: int = 0
    message: str = "ok"
    data: Any | None = None


class TypeResult(BaseModel):
    type: int
    name: str
    detail: list[dict[str, Any]]


class CallbackPayload(BaseModel):
    registrationId: str
    results: list[TypeResult]


class TaskRecord(BaseModel):
    task_id: str
    status: TaskStatus
    registration_id: str | None = None
    stage: str = TaskStage.ACCEPTED
    progress: int = 0
    steps: list[TaskStep] = Field(default_factory=list)
    error: str | None = None
    result: CallbackPayload | None = None
    doc_type: int | None = None
    doc_type_name: str | None = None
    file_size: int | None = None
    file_format: str | None = None
    file_name: str | None = None
    has_stored_file: bool = False
    duration_ms: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class TaskSummary(BaseModel):
    taskId: str
    registrationId: str | None = None
    status: TaskStatus
    stage: str
    progress: int
    hasResult: bool = False
    docType: int | None = None
    docTypeName: str | None = None
    fileFormat: str | None = None
    fileName: str | None = None
    hasStoredFile: bool = False
    fileSize: int | None = None
    durationMs: int | None = None
    createdAt: str
    updatedAt: str


class TaskListResponse(BaseModel):
    items: list[TaskSummary]
    total: int
    page: int
    pageSize: int


class TaskStatusResponse(BaseModel):
    taskId: str
    status: TaskStatus
    registrationId: str | None = None
    stage: str | None = None
    progress: int = 0
    steps: list[TaskStep] = Field(default_factory=list)
    error: str | None = None
    result: CallbackPayload | None = None
    createdAt: str | None = None
    updatedAt: str | None = None
    fileName: str | None = None
    hasStoredFile: bool = False
