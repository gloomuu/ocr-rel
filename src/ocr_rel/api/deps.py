from fastapi import Header, HTTPException, status

from ocr_rel.auth.token import compute_auth_token, is_auth_configured
from ocr_rel.config import settings


def expected_auth_token() -> str:
    return compute_auth_token(
        settings.auth_username,
        settings.auth_password,
        settings.auth_secret_key,
    )


async def verify_api_auth(
    token: str | None = Header(default=None, alias="token"),
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> None:
    if not settings.auth_enabled:
        return

    if not is_auth_configured(
        settings.auth_username,
        settings.auth_password,
        settings.auth_secret_key,
    ):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication is enabled but credentials are not configured",
        )

    provided = (token or "").strip()
    if not provided and authorization and authorization.lower().startswith("bearer "):
        provided = authorization[7:].strip()
    if not provided and x_api_key:
        provided = x_api_key.strip()

    if provided != expected_auth_token():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
