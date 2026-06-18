from __future__ import annotations

import base64
import io
from typing import Any

import httpx
from PIL import Image

from ocr_rel.config import settings
from ocr_rel.logging_config import get_logger
from ocr_rel.ocr.base import OcrEngine

logger = get_logger(__name__)


class LocalHttpOcrClient:
    """Call a locally deployed OCR HTTP service (POST /ocr/single)."""

    def __init__(
        self,
        *,
        server_url: str | None = None,
        timeout: float | None = None,
        confidence_threshold: float | None = None,
    ) -> None:
        self._server_url = (server_url or settings.ocr_server_url).rstrip("/")
        self._timeout = timeout if timeout is not None else settings.ocr_timeout
        self._confidence_threshold = (
            confidence_threshold
            if confidence_threshold is not None
            else settings.ocr_confidence_threshold
        )

    async def recognize_image(self, image: Image.Image) -> str:
        blocks = await self.recognize_blocks(self.encode_image(image))
        return self.blocks_to_text(blocks)

    async def recognize_blocks(self, image_base64: str) -> list[dict[str, Any]]:
        url = f"{self._server_url}/ocr/single"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(url, json={"image": image_base64})
                response.raise_for_status()
                payload = response.json()
        except httpx.ConnectError as exc:
            raise ConnectionError(f"无法连接 OCR 服务: {self._server_url}") from exc
        except httpx.TimeoutException as exc:
            raise TimeoutError(f"OCR 服务超时: {self._server_url}") from exc

        result = payload.get("result", {})
        if not isinstance(result, dict):
            return []
        blocks = result.get("words_block_list", [])
        if not isinstance(blocks, list):
            return []
        return blocks

    def blocks_to_text(
        self,
        blocks: list[dict[str, Any]],
        *,
        min_confidence: float | None = None,
    ) -> str:
        threshold = self._confidence_threshold if min_confidence is None else min_confidence
        lines: list[str] = []
        for block in blocks:
            score = float(block.get("confidence", 0) or 0)
            text = str(block.get("words", "")).strip()
            if score > threshold and text:
                lines.append(text)
        return "\n".join(lines)

    @staticmethod
    def encode_image(image: Image.Image, *, image_format: str = "PNG") -> str:
        buffer = io.BytesIO()
        image.convert("RGB").save(buffer, format=image_format)
        return base64.b64encode(buffer.getvalue()).decode("utf-8")


class LocalHttpOcrEngine(OcrEngine):
    """OcrEngine adapter for LocalHttpOcrClient."""

    def __init__(self, client: LocalHttpOcrClient | None = None) -> None:
        self._client = client or LocalHttpOcrClient()

    async def recognize_image(self, image: Image.Image) -> str:
        return await self._client.recognize_image(image)
