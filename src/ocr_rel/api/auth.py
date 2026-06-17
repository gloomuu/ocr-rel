from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from ocr_rel.auth.token import compute_auth_token, is_auth_configured
from ocr_rel.config import settings
from ocr_rel.models.schemas import ApiResponse

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class AuthTokenRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


@router.post("/token", response_model=ApiResponse)
async def issue_auth_token(request: AuthTokenRequest) -> ApiResponse:
    if not settings.auth_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Authentication is disabled",
        )

    if not is_auth_configured(
        settings.auth_username,
        settings.auth_password,
        settings.auth_secret_key,
    ):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication is enabled but credentials are not configured",
        )

    if (
        request.username != settings.auth_username
        or request.password != settings.auth_password
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")

    token = compute_auth_token(
        settings.auth_username,
        settings.auth_password,
        settings.auth_secret_key,
    )
    return ApiResponse(data={"token": token})
