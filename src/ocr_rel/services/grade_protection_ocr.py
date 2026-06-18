from __future__ import annotations

from typing import Any

from PIL import Image

from ocr_rel.config import settings
from ocr_rel.llm.extractor import LlmExtractor
from ocr_rel.logging_config import get_logger, log_step
from ocr_rel.ocr.base import OcrEngine
from ocr_rel.parsers.type6_grade_protection import extract_grade_protection_detail

logger = get_logger(__name__)

GRADE_PROTECTION_FIELD_KEYS = ("companyName", "systemLevel")


def merge_page_texts(page_texts: list[str]) -> str:
    parts: list[str] = []
    for page_number, page_text in enumerate(page_texts, start=1):
        stripped = page_text.strip()
        if stripped:
            parts.append(f"--- 第 {page_number} 页 ---\n{stripped}")
    return "\n\n".join(parts)


def _merge_detail(llm_detail: dict[str, str], regex_detail: dict[str, str]) -> dict[str, str]:
    merged = dict(regex_detail)
    for key in GRADE_PROTECTION_FIELD_KEYS:
        merged[key] = llm_detail.get(key, "").strip() or regex_detail.get(key, "").strip()
    merged["copyrightOwner"] = ""
    return merged


async def _extract_grade_protection_fields(
    full_text: str,
    llm_extractor: LlmExtractor,
    *,
    task_id: str | None = None,
    registration_id: str | None = None,
) -> dict[str, Any]:
    regex_detail = extract_grade_protection_detail(full_text)

    if llm_extractor.is_available:
        try:
            log_step(
                logger,
                task_id=task_id,
                registration_id=registration_id,
                step="llm.grade_protection.start",
                message="提交等保备案全文至大模型提取字段",
                textLength=len(full_text),
            )
            llm_detail = await llm_extractor.extract_grade_protection_fields(full_text)
            detail = _merge_detail(llm_detail, regex_detail)
            log_step(
                logger,
                task_id=task_id,
                registration_id=registration_id,
                step="llm.grade_protection.done",
                message="大模型已提取等保备案字段",
                detail={key: detail.get(key, "") for key in GRADE_PROTECTION_FIELD_KEYS},
            )
            return detail
        except Exception as exc:
            log_step(
                logger,
                task_id=task_id,
                registration_id=registration_id,
                step="llm.grade_protection.failed",
                message=str(exc),
            )
            if not settings.llm_fallback_to_regex:
                return regex_detail

    log_step(
        logger,
        task_id=task_id,
        registration_id=registration_id,
        step="regex.grade_protection.done",
        message="规则已提取等保备案字段",
        detail={key: regex_detail.get(key, "") for key in GRADE_PROTECTION_FIELD_KEYS},
    )
    return regex_detail


async def recognize_grade_protection_detail(
    engine: OcrEngine,
    images: list[Image.Image],
    *,
    llm_extractor: LlmExtractor | None = None,
    task_id: str | None = None,
    registration_id: str | None = None,
) -> tuple[dict[str, Any], str]:
    """OCR the full grade-protection document and extract companyName/systemLevel."""
    if not images:
        raise ValueError("Grade protection PDF contains no pages")

    llm = llm_extractor or LlmExtractor()

    log_step(
        logger,
        task_id=task_id,
        registration_id=registration_id,
        step="grade_protection.full_doc.start",
        message="等保备案启用全文 OCR（合并后提交大模型）",
        totalPages=len(images),
    )

    page_texts: list[str] = []
    for page_number, image in enumerate(images, start=1):
        page_text = (await engine.recognize_image(image)).strip()
        page_texts.append(page_text)
        log_step(
            logger,
            task_id=task_id,
            registration_id=registration_id,
            step="ocr.grade_protection.page.done",
            message="等保备案分页 OCR 完成",
            page=page_number,
            textLength=len(page_text),
        )

    full_text = merge_page_texts(page_texts)
    if not full_text.strip():
        raise ValueError("OCR returned empty text for grade protection document")

    detail = await _extract_grade_protection_fields(
        full_text,
        llm,
        task_id=task_id,
        registration_id=registration_id,
    )
    log_step(
        logger,
        task_id=task_id,
        registration_id=registration_id,
        step="grade_protection.full_doc.done",
        message="等保备案全文识别完成",
        totalPages=len(images),
        textLength=len(full_text),
        detail={key: detail.get(key, "") for key in GRADE_PROTECTION_FIELD_KEYS},
    )
    return detail, full_text
