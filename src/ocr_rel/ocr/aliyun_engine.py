import asyncio
import json
from io import BytesIO

from alibabacloud_ocr_api20210707 import models as ocr_models
from alibabacloud_ocr_api20210707.client import Client as OcrClient
from alibabacloud_tea_openapi import models as open_api_models
from PIL import Image

from ocr_rel.config import settings
from ocr_rel.logging_config import get_logger
from ocr_rel.ocr.base import OcrEngine

logger = get_logger(__name__)

MAX_IMAGE_SIDE = 4096
MAX_IMAGE_BYTES = 1_500_000


def prepare_image_bytes(image: Image.Image) -> BytesIO:
    """Convert PIL image to JPEG bytes for Aliyun OCR (raw binary, not base64)."""
    img = image.convert("RGB")
    width, height = img.size
    max_side = max(width, height)
    if max_side > MAX_IMAGE_SIDE:
        scale = MAX_IMAGE_SIDE / max_side
        img = img.resize(
            (max(1, int(width * scale)), max(1, int(height * scale))),
            Image.Resampling.LANCZOS,
        )

    quality = 95
    buffer = BytesIO()
    while True:
        buffer = BytesIO()
        img.save(buffer, format="JPEG", quality=quality, optimize=True)
        if buffer.tell() <= MAX_IMAGE_BYTES or quality <= 60:
            break
        quality -= 10

    buffer.seek(0)
    return buffer


def parse_recognize_general_response(data: str | None) -> str:
    if not data:
        return ""
    try:
        parsed = json.loads(data)
    except json.JSONDecodeError:
        return data
    if isinstance(parsed, dict):
        return str(parsed.get("content") or "")
    return data


class AliyunOcrEngine(OcrEngine):
    def __init__(self) -> None:
        if not settings.aliyun_access_key_id or not settings.aliyun_access_key_secret:
            raise ValueError("Aliyun OCR credentials are not configured")
        config = open_api_models.Config(
            access_key_id=settings.aliyun_access_key_id,
            access_key_secret=settings.aliyun_access_key_secret,
            endpoint=settings.aliyun_ocr_endpoint,
        )
        self._client = OcrClient(config)

    async def recognize_image(self, image: Image.Image) -> str:
        return await asyncio.to_thread(self._recognize_sync, image)

    def _recognize_sync(self, image: Image.Image) -> str:
        image_file = prepare_image_bytes(image)
        request = ocr_models.RecognizeGeneralRequest(body=image_file)
        response = self._client.recognize_general(request)
        body = response.body
        if body is None:
            return ""
        if body.code and body.code not in {"200", ""}:
            raise RuntimeError(
                f"Aliyun OCR failed: code={body.code}, message={body.message}"
            )
        return parse_recognize_general_response(body.data)
