import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from ocr_rel.api.deps import verify_api_auth
from ocr_rel.api.tasks import _to_task_response
from ocr_rel.config import settings
from ocr_rel.models.schemas import (
    ATTACHMENT_TYPE_NAMES,
    ApiResponse,
    FileRef,
    FileTypeGroup,
    RecognizeRequest,
)
from ocr_rel.parsers.registry import supported_types
from ocr_rel.pdf.converter import detect_file_format_label
from ocr_rel.services.local_file_store import local_file_store
from ocr_rel.services.recognition_service import recognition_service
from ocr_rel.services.task_manager import task_manager
from ocr_rel.services.test_file_store import test_file_store
from ocr_rel.services.upload_validation import validate_upload_size
from ocr_rel.tasks.runner import background_runner

router = APIRouter(prefix="/api/v1/test", tags=["test"])


@router.get("/supported-types", response_model=ApiResponse, dependencies=[Depends(verify_api_auth)])
async def list_supported_types() -> ApiResponse:
    types = supported_types()
    items = [
        {
            "type": doc_type,
            "name": ATTACHMENT_TYPE_NAMES.get(doc_type, f"type-{doc_type}"),
        }
        for doc_type in types
    ]
    return ApiResponse(data={"types": types, "items": items})


@router.get("/config", response_model=ApiResponse)
async def get_test_config() -> ApiResponse:
    """Return test page defaults from server configuration."""
    types = supported_types()
    supported_type_items = [
        {
            "type": doc_type,
            "name": ATTACHMENT_TYPE_NAMES.get(doc_type, f"type-{doc_type}"),
        }
        for doc_type in types
    ]
    return ApiResponse(
        data={
            "ocrEngine": settings.test_page_default_ocr_engine,
            "maxConcurrentTasks": settings.max_concurrent_tasks,
            "maxUploadFileSize": settings.max_upload_file_size,
            "maxStoredFiles": settings.max_stored_files,
            "serverOcrEngine": settings.ocr_engine,
            "authEnabled": settings.auth_enabled,
            "supportedTypes": types,
            "supportedTypeItems": supported_type_items,
        }
    )


@router.post("/recognize", response_model=ApiResponse, dependencies=[Depends(verify_api_auth)])
async def test_recognize(
    registration_id: str = Form(...),
    doc_type: int = Form(...),
    attachment_name: str | None = Form(default=None),
    file: UploadFile = File(...),
    personnel: str | None = Form(default=None),
    ocr_engine: str | None = Form(default=None),
) -> ApiResponse:
    """模拟业务侧调用 POST /api/v1/recognize，本地文件映射为 uuid 下载。"""
    if doc_type not in supported_types():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Document type {doc_type} is not supported yet. Supported: {supported_types()}",
        )

    content = await file.read()
    validate_upload_size(content, filename=file.filename)

    file_uuid = str(uuid.uuid4())
    file_name = file.filename or "upload.bin"
    await test_file_store.put(
        file_uuid,
        file_name=file_name,
        content=content,
    )

    type_name = attachment_name or ATTACHMENT_TYPE_NAMES.get(doc_type, f"type-{doc_type}")
    request = RecognizeRequest(
        registrationId=registration_id,
        files=[
            FileTypeGroup(
                type=doc_type,
                name=type_name,
                files=[FileRef(uuid=file_uuid, personnel=personnel)],
            )
        ],
    )

    engine = (ocr_engine or settings.ocr_engine).lower()
    record = await task_manager.create_task(
        registration_id=registration_id,
        doc_type=doc_type,
        doc_type_name=type_name,
        file_size=len(content),
        file_format=detect_file_format_label(content, file_name),
        file_name=file_name,
    )
    await local_file_store.save(record.task_id, file_name=file_name, content=content)

    async def download_file(file_uuid: str) -> tuple[str, bytes]:
        return await test_file_store.get(file_uuid)

    background_runner.run(
        recognition_service.process_test_recognize_request(
            record.task_id,
            request,
            ocr_engine=engine,
            download_file=download_file,
        ),
        task_id=record.task_id,
    )

    return ApiResponse(
        message="accepted",
        data={
            "taskId": record.task_id,
            "registrationId": registration_id,
            "ocrEngine": engine,
            "requestEcho": request.model_dump(),
        },
    )


@router.post("/parse", response_model=ApiResponse, dependencies=[Depends(verify_api_auth)])
async def parse_local_file(
    file: UploadFile = File(...),
    doc_type: int = Form(...),
    registration_id: str = Form(default="test-registration"),
    personnel: str | None = Form(default=None),
    ocr_engine: str | None = Form(default=None),
) -> ApiResponse:
    """兼容旧接口：直传文件解析（不走 uuid 下载模拟）。"""
    if doc_type not in supported_types():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Document type {doc_type} is not supported yet. Supported: {supported_types()}",
        )

    content = await file.read()
    validate_upload_size(content, filename=file.filename)

    engine = (ocr_engine or settings.ocr_engine).lower()
    type_name = ATTACHMENT_TYPE_NAMES.get(doc_type, f"type-{doc_type}")
    file_name = file.filename or "upload.bin"
    record = await task_manager.create_task(
        registration_id=registration_id,
        doc_type=doc_type,
        doc_type_name=type_name,
        file_size=len(content),
        file_format=detect_file_format_label(content, file_name),
        file_name=file_name,
    )
    await local_file_store.save(record.task_id, file_name=file_name, content=content)
    background_runner.run(
        recognition_service.process_local_file(
            record.task_id,
            registration_id=registration_id,
            doc_type=doc_type,
            file_bytes=content,
            filename=file_name,
            ocr_engine=engine,
            personnel=personnel,
        ),
        task_id=record.task_id,
    )
    return ApiResponse(
        data={"taskId": record.task_id, "ocrEngine": engine},
        message="accepted",
    )


@router.get("/tasks/{task_id}", response_model=ApiResponse, dependencies=[Depends(verify_api_auth)])
async def get_task_result(task_id: str) -> ApiResponse:
    record = await task_manager.get_task(task_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return ApiResponse(data=_to_task_response(record).model_dump())
