from fastapi import APIRouter, Depends

from ocr_rel.api.deps import verify_api_auth
from ocr_rel.logging_config import get_logger, log_step
from ocr_rel.models.schemas import ApiResponse, RecognizeRequest, RecognizeResponse, ATTACHMENT_TYPE_NAMES
from ocr_rel.services.recognition_service import recognition_service
from ocr_rel.services.task_manager import task_manager
from ocr_rel.tasks.runner import background_runner

router = APIRouter(prefix="/api/v1", tags=["recognize"])
logger = get_logger(__name__)


@router.post("/recognize", response_model=ApiResponse)
async def recognize(
    request: RecognizeRequest,
    _: None = Depends(verify_api_auth),
) -> ApiResponse:
    log_step(
        logger,
        registration_id=request.registrationId,
        step="api.recognize",
        message="收到识别 API 请求",
        fileGroups=len(request.files),
    )
    first_group = request.files[0] if request.files else None
    doc_type = first_group.type if first_group else None
    doc_type_name = (
        (first_group.name if first_group else None)
        or (ATTACHMENT_TYPE_NAMES.get(doc_type) if doc_type else None)
    )
    record = await task_manager.create_task(
        registration_id=request.registrationId,
        doc_type=doc_type,
        doc_type_name=doc_type_name,
    )
    background_runner.run(
        recognition_service.process_recognize_request(record.task_id, request),
        task_id=record.task_id,
    )
    return ApiResponse(
        data=RecognizeResponse(taskId=record.task_id).model_dump(),
        message="accepted",
    )
