from __future__ import annotations

from PIL import Image

from ocr_rel.config import settings
from ocr_rel.logging_config import get_logger
from ocr_rel.ocr.aliyun_engine import AliyunOcrEngine
from ocr_rel.ocr.base import OcrEngine
from ocr_rel.ocr.seal_region import crop_business_license_seal_region
from ocr_rel.ocr.paddle_engine import PaddleOcrEngine

logger = get_logger(__name__)

_engines: dict[str, OcrEngine] = {}


def get_ocr_engine(engine_name: str | None = None) -> OcrEngine:
    name = (engine_name or settings.ocr_engine).lower()
    if name not in {"paddle", "aliyun"}:
        raise ValueError(f"Unsupported OCR engine: {name}")

    if name not in _engines:
        if name == "paddle":
            _engines[name] = PaddleOcrEngine()
        else:
            try:
                _engines[name] = AliyunOcrEngine()
            except ValueError as exc:
                logger.warning("Aliyun OCR unavailable (%s), falling back to PaddleOCR", exc)
                _engines[name] = PaddleOcrEngine()
    return _engines[name]


async def recognize_business_license_text(engine: OcrEngine, images: list[Image.Image]) -> str:
    """Run full-page OCR plus a bottom-right seal crop to capture stamp text."""
    parts: list[str] = []
    for image in images:
        page_text = (await engine.recognize_image(image)).strip()
        if page_text:
            parts.append(page_text)
        seal_image = crop_business_license_seal_region(image)
        seal_text = (await engine.recognize_image(seal_image)).strip()
        if seal_text:
            parts.append(seal_text)
    return "\n".join(parts)
