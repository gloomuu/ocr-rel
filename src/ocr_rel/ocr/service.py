from __future__ import annotations

from dataclasses import dataclass

from PIL import Image

from ocr_rel.config import settings
from ocr_rel.logging_config import get_logger
from ocr_rel.ocr.aliyun_engine import AliyunOcrEngine
from ocr_rel.ocr.base import OcrEngine
from ocr_rel.ocr.local_engine import LocalHttpOcrEngine
from ocr_rel.ocr.seal_region import crop_business_license_seal_region
from ocr_rel.ocr.paddle_engine import PaddleOcrEngine

logger = get_logger(__name__)

_engines: dict[str, OcrEngine] = {}


def get_ocr_engine(engine_name: str | None = None) -> OcrEngine:
    name = (engine_name or settings.ocr_engine).lower()
    if name not in {"local", "paddle", "aliyun"}:
        raise ValueError(f"Unsupported OCR engine: {name}")

    if name not in _engines:
        if name == "local":
            _engines[name] = LocalHttpOcrEngine()
        elif name == "paddle":
            _engines[name] = PaddleOcrEngine()
        else:
            try:
                _engines[name] = AliyunOcrEngine()
            except ValueError as exc:
                logger.warning("Aliyun OCR unavailable (%s), falling back to local HTTP OCR", exc)
                _engines[name] = LocalHttpOcrEngine()
    return _engines[name]


@dataclass(frozen=True)
class BusinessLicenseOcrResult:
    page_text: str
    seal_text: str
    seal_images: tuple[Image.Image, ...] = ()

    @property
    def combined_text(self) -> str:
        parts = [self.page_text.strip(), self.seal_text.strip()]
        return "\n".join(part for part in parts if part)


async def recognize_business_license_ocr(
    engine: OcrEngine,
    images: list[Image.Image],
) -> BusinessLicenseOcrResult:
    """Run full-page OCR plus a bottom-right seal crop to capture stamp text."""
    page_parts: list[str] = []
    seal_parts: list[str] = []
    seal_images: list[Image.Image] = []
    for image in images:
        page_text = (await engine.recognize_image(image)).strip()
        if page_text:
            page_parts.append(page_text)
        seal_image = crop_business_license_seal_region(image)
        seal_images.append(seal_image)
        seal_text = (await engine.recognize_image(seal_image)).strip()
        if seal_text:
            seal_parts.append(seal_text)
    return BusinessLicenseOcrResult(
        page_text="\n".join(page_parts),
        seal_text="\n".join(seal_parts),
        seal_images=tuple(seal_images),
    )


async def recognize_business_license_text(engine: OcrEngine, images: list[Image.Image]) -> str:
    return (await recognize_business_license_ocr(engine, images)).combined_text
