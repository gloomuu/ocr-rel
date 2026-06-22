import asyncio

import httpx

from ocr_rel.clients.platform_utils import is_platform_success_code
from ocr_rel.config import settings
from ocr_rel.logging_config import get_logger, log_step
from ocr_rel.models.schemas import CallbackPayload
from ocr_rel.services.callback_serializer import serialize_callback_payload

logger = get_logger(__name__)


class PlatformCallbackClient:
    def __init__(self) -> None:
        self._base_url = settings.platform_base_url.rstrip("/")
        self._api_key = settings.platform_api_key
        self._retry_count = settings.platform_callback_retry_count
        self._retry_interval = settings.platform_callback_retry_interval

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    async def send_callback(self, payload: CallbackPayload) -> None:
        if not settings.platform_callback_enabled:
            log_step(
                logger,
                registration_id=payload.registrationId,
                step="callback.skipped",
                message="平台回调未启用，跳过",
            )
            return

        url = f"{self._base_url}/api/ai/result/callback"
        body = serialize_callback_payload(payload)
        log_step(
            logger,
            registration_id=payload.registrationId,
            step="callback.request",
            message="发送回调请求",
            url=url,
        )

        for attempt in range(1, self._retry_count + 1):
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    response = await client.post(url, json=body, headers=self._headers())
                    response.raise_for_status()
                    result = response.json()
                code = result.get("code", 0)
                if is_platform_success_code(code):
                    log_step(
                        logger,
                        registration_id=payload.registrationId,
                        step="callback.success",
                        message=f"回调成功 attempt={attempt}",
                    )
                    return
                logger.warning(
                    "Callback returned non-zero code=%s for registrationId=%s attempt=%s",
                    code,
                    payload.registrationId,
                    attempt,
                )
            except Exception as exc:
                logger.warning(
                    "Callback failed for registrationId=%s attempt=%s: %s",
                    payload.registrationId,
                    attempt,
                    exc,
                )

            if attempt < self._retry_count:
                await asyncio.sleep(self._retry_interval)

        raise RuntimeError(
            f"Callback failed after {self._retry_count} attempts for {payload.registrationId}"
        )
