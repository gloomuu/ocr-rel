from __future__ import annotations

from typing import Any

from PIL import Image

from ocr_rel.config import settings
from ocr_rel.llm.extractor import LlmExtractor
from ocr_rel.logging_config import get_logger, log_step
from ocr_rel.ocr.base import OcrEngine
from ocr_rel.parsers.type6_software_copyright import extract_software_copyright_detail

logger = get_logger(__name__)

SOFTWARE_COPYRIGHT_FIELD_KEYS = ("copyrightOwner",)


def _merge_detail(llm_detail: dict[str, str], regex_detail: dict[str, str]) -> dict[str, str]:
    merged = dict(regex_detail)
    merged["copyrightOwner"] = (
        llm_detail.get("copyrightOwner", "").strip() or regex_detail.get("copyrightOwner", "").strip()
    )
    merged["companyName"] = ""
    merged["systemLevel"] = ""
    return merged


async def _extract_software_copyright_fields(
    cover_text: str,
    llm_extractor: LlmExtractor,
    *,
    task_id: str | None = None,
    registration_id: str | None = None,
) -> dict[str, Any]:
    regex_detail = extract_software_copyright_detail(cover_text)

    if llm_extractor.is_available:
        try:
            log_step(
                logger,
                task_id=task_id,
                registration_id=registration_id,
                step="llm.software_copyright.start",
                message="提交软著证书首页至大模型提取字段",
                textLength=len(cover_text),
            )
            llm_detail = await llm_extractor.extract_software_copyright_fields(cover_text)
            detail = _merge_detail(llm_detail, regex_detail)
            log_step(
                logger,
                task_id=task_id,
                registration_id=registration_id,
                step="llm.software_copyright.done",
                message="大模型已提取软著证书字段",
                detail={key: detail.get(key, "") for key in SOFTWARE_COPYRIGHT_FIELD_KEYS},
            )
            return detail
        except Exception as exc:
            log_step(
                logger,
                task_id=task_id,
                registration_id=registration_id,
                step="llm.software_copyright.failed",
                message=str(exc),
            )
            if not settings.llm_fallback_to_regex:
                return regex_detail

    log_step(
        logger,
        task_id=task_id,
        registration_id=registration_id,
        step="regex.software_copyright.done",
        message="规则已提取软著证书字段",
        detail={key: regex_detail.get(key, "") for key in SOFTWARE_COPYRIGHT_FIELD_KEYS},
    )
    return regex_detail


async def recognize_software_copyright_detail(
    engine: OcrEngine,
    images: list[Image.Image],
    *,
    cover_text: str | None = None,
    llm_extractor: LlmExtractor | None = None,
    task_id: str | None = None,
    registration_id: str | None = None,
) -> tuple[dict[str, Any], str]:
    """Extract software copyright fields from the cover page only."""
    if not images:
        raise ValueError("Software copyright PDF contains no pages")

    llm = llm_extractor or LlmExtractor()
    text = (cover_text or (await engine.recognize_image(images[0])).strip()).strip()
    if not text:
        raise ValueError("OCR returned empty text on software copyright cover page")

    log_step(
        logger,
        task_id=task_id,
        registration_id=registration_id,
        step="software_copyright.cover_only.start",
        message="软著证书仅 OCR 第 1 页",
        inputPages=len(images),
        ocrPage=1,
        textLength=len(text),
    )

    detail = await _extract_software_copyright_fields(
        text,
        llm,
        task_id=task_id,
        registration_id=registration_id,
    )
    log_step(
        logger,
        task_id=task_id,
        registration_id=registration_id,
        step="software_copyright.cover_only.done",
        message="软著证书首页识别完成",
        detail={key: detail.get(key, "") for key in SOFTWARE_COPYRIGHT_FIELD_KEYS},
    )
    return detail, text
