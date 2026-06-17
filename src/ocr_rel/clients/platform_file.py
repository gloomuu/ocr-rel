import base64

import httpx

from ocr_rel.config import settings
from ocr_rel.logging_config import get_logger

logger = get_logger(__name__)


class PlatformFileClient:
    def __init__(self) -> None:
        self._base_url = settings.platform_base_url.rstrip("/")
        self._api_key = settings.platform_api_key

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    async def download_file(self, file_uuid: str) -> tuple[str, bytes]:
        url = f"{self._base_url}/api/ai/file/download"
        payload = {"uuid": file_uuid}
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, json=payload, headers=self._headers())
            response.raise_for_status()
            body = response.json()

        code = body.get("code", 0)
        if code == 1001:
            raise ValueError(f"File UUID invalid or expired: {file_uuid}")
        if code != 0:
            raise ValueError(body.get("message") or f"Download failed with code {code}")

        data = body.get("data") or {}
        file_name = data.get("fileName") or f"{file_uuid}.pdf"
        base64_content = data.get("base64Content")
        if not base64_content:
            raise ValueError(f"Missing base64Content for UUID: {file_uuid}")

        return file_name, base64.b64decode(base64_content)
