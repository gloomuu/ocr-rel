from __future__ import annotations

from fastapi import HTTPException, status

from ocr_rel.logging_config import get_logger, log_step
from ocr_rel.models.schemas import ATTACHMENT_TYPE_NAMES, RecognizeRequest
from ocr_rel.parsers.registry import supported_types
from ocr_rel.services.recognition_service import recognition_service
from ocr_rel.services.task_manager import task_manager
from ocr_rel.tasks.runner import background_runner

logger = get_logger(__name__)


def validate_recognize_request_types(request: RecognizeRequest) -> None:
    supported = set(supported_types())
    unsupported = sorted({group.type for group in request.files if group.type not in supported})
    if unsupported:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "Document type is not supported yet",
                "unsupportedTypes": unsupported,
                "supportedTypes": sorted(supported),
            },
        )


async def submit_recognize_request(
    request: RecognizeRequest,
    *,
    step: str,
    message: str,
) -> str:
    validate_recognize_request_types(request)

    log_step(
        logger,
        registration_id=request.registrationId,
        step=step,
        message=message,
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
    return record.task_id
