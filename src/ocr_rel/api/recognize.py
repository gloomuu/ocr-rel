from fastapi import APIRouter, Depends

from ocr_rel.api.deps import verify_api_auth
from ocr_rel.models.schemas import ApiResponse, RecognizeRequest, RecognizeResponse
from ocr_rel.services.submit_service import submit_recognize_request

router = APIRouter(prefix="/api/v1", tags=["recognize"])


@router.post("/recognize", response_model=ApiResponse)
async def recognize(
    request: RecognizeRequest,
    _: None = Depends(verify_api_auth),
) -> ApiResponse:
    task_id = await submit_recognize_request(
        request,
        step="api.recognize",
        message="收到识别 API 请求",
    )
    return ApiResponse(
        data=RecognizeResponse(taskId=task_id).model_dump(),
        message="accepted",
    )
