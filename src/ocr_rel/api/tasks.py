from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse

from ocr_rel.api.deps import verify_api_auth
from ocr_rel.models.schemas import ApiResponse, TaskListResponse, TaskStatus, TaskStatusResponse
from ocr_rel.services.local_file_store import local_file_store
from ocr_rel.services.task_manager import task_manager

router = APIRouter(
    prefix="/api/v1/tasks",
    tags=["tasks"],
    dependencies=[Depends(verify_api_auth)],
)


def _to_task_response(record) -> TaskStatusResponse:
    return TaskStatusResponse(
        taskId=record.task_id,
        status=record.status,
        registrationId=record.registration_id,
        stage=record.stage,
        progress=record.progress,
        steps=[step.model_copy() for step in record.steps],
        error=record.error,
        result=record.result,
        createdAt=record.created_at.isoformat() if record.created_at else None,
        updatedAt=record.updated_at.isoformat() if record.updated_at else None,
        fileName=record.file_name,
        hasStoredFile=record.has_stored_file,
    )


@router.get("", response_model=ApiResponse)
async def list_tasks(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100, alias="pageSize"),
    registration_id: str | None = Query(default=None, alias="registrationId"),
) -> ApiResponse:
    items, total = await task_manager.list_tasks(
        page=page,
        page_size=page_size,
        registration_id=registration_id,
    )
    response = TaskListResponse(
        items=items,
        total=total,
        page=page,
        pageSize=page_size,
    )
    return ApiResponse(data=response.model_dump())


@router.get("/{task_id}", response_model=ApiResponse)
async def get_task(task_id: str) -> ApiResponse:
    record = await task_manager.get_task(task_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return ApiResponse(data=_to_task_response(record).model_dump())


@router.get("/{task_id}/callback", response_model=ApiResponse)
async def get_task_callback(task_id: str) -> ApiResponse:
    record = await task_manager.get_task(task_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    if record.status != TaskStatus.SUCCESS or record.result is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Task is not ready for callback view, status={record.status}",
        )
    return ApiResponse(data=record.result.model_dump())


@router.get("/{task_id}/file")
async def get_task_file(task_id: str) -> FileResponse:
    record = await task_manager.get_task(task_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    stored = await local_file_store.get_file_path(task_id)
    if stored is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stored file not found")

    file_path, file_name = stored
    return FileResponse(
        path=str(file_path),
        media_type=local_file_store.media_type_for(file_name),
        filename=file_name,
        content_disposition_type="inline",
    )
