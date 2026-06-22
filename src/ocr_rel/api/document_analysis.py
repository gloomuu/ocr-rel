from fastapi import APIRouter, Depends

from ocr_rel.api.deps import verify_api_auth
from ocr_rel.models.schemas import DocumentAnalysisSubmitData, DocumentAnalysisSubmitResponse, RecognizeRequest
from ocr_rel.services.submit_service import submit_recognize_request

router = APIRouter(prefix="/v1/document/analysis", tags=["document-analysis"])


@router.post("/submit", response_model=DocumentAnalysisSubmitResponse)
async def submit_document_analysis(
    request: RecognizeRequest,
    _: None = Depends(verify_api_auth),
) -> DocumentAnalysisSubmitResponse:
    task_id = await submit_recognize_request(
        request,
        step="api.document_analysis.submit",
        message="收到对外文档分析提交请求",
    )
    return DocumentAnalysisSubmitResponse(
        data=DocumentAnalysisSubmitData(
            taskId=task_id,
            registrationId=request.registrationId,
        ),
        message="accepted",
    )
