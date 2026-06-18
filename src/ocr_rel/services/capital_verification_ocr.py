from __future__ import annotations

from typing import Any

from PIL import Image

from ocr_rel.config import settings
from ocr_rel.llm.extractor import LlmExtractor
from ocr_rel.logging_config import get_logger, log_step
from ocr_rel.ocr.base import OcrEngine
from ocr_rel.parsers.type3_audit_report import is_invalid_accounting_firm_name
from ocr_rel.parsers.type4_capital_verification import extract_cover_fields

logger = get_logger(__name__)

COVER_FIELD_KEYS = ("companyName", "accountingFirmName", "reportCode")


def _merge_cover_fields(llm_detail: dict[str, str], regex_detail: dict[str, str]) -> dict[str, str]:
    merged = dict(regex_detail)

    for key in COVER_FIELD_KEYS:
        llm_value = llm_detail.get(key, "").strip()
        regex_value = regex_detail.get(key, "").strip()

        if key == "accountingFirmName":
            if llm_value and not is_invalid_accounting_firm_name(llm_value):
                merged[key] = llm_value
            elif regex_value and not is_invalid_accounting_firm_name(regex_value):
                merged[key] = regex_value
            else:
                merged[key] = ""
            continue

        merged[key] = llm_value or regex_value

    return merged


async def _extract_cover_fields(
    cover_text: str,
    llm_extractor: LlmExtractor,
    *,
    task_id: str | None = None,
    registration_id: str | None = None,
) -> dict[str, Any]:
    regex_detail = extract_cover_fields(cover_text)

    if llm_extractor.is_available:
        try:
            log_step(
                logger,
                task_id=task_id,
                registration_id=registration_id,
                step="llm.capital.cover.start",
                message="提交验资报告首页至大模型提取封面字段",
                textLength=len(cover_text),
            )
            llm_detail = await llm_extractor.extract_capital_verification_cover_fields(cover_text)
            detail = _merge_cover_fields(llm_detail, regex_detail)
            log_step(
                logger,
                task_id=task_id,
                registration_id=registration_id,
                step="llm.capital.cover.done",
                message="大模型已提取验资报告封面字段",
                detail={key: detail.get(key, "") for key in COVER_FIELD_KEYS},
            )
            return detail
        except Exception as exc:
            log_step(
                logger,
                task_id=task_id,
                registration_id=registration_id,
                step="llm.capital.cover.failed",
                message=str(exc),
            )
            if not settings.llm_fallback_to_regex:
                return regex_detail

    log_step(
        logger,
        task_id=task_id,
        registration_id=registration_id,
        step="regex.capital.cover.done",
        message="规则已提取验资报告封面字段",
        detail={key: regex_detail.get(key, "") for key in COVER_FIELD_KEYS},
    )
    return regex_detail


async def recognize_capital_verification_detail(
    engine: OcrEngine,
    images: list[Image.Image],
    *,
    llm_extractor: LlmExtractor | None = None,
    task_id: str | None = None,
    registration_id: str | None = None,
) -> tuple[dict[str, Any], str]:
    """Extract type-4 fields from the first page only (cover/home page)."""
    if not images:
        raise ValueError("Capital verification report PDF contains no pages")

    llm = llm_extractor or LlmExtractor()

    log_step(
        logger,
        task_id=task_id,
        registration_id=registration_id,
        step="capital.cover_only.start",
        message="验资报告仅 OCR 第 1 页",
        inputPages=len(images),
        ocrPage=1,
        skippedPages=max(0, len(images) - 1),
    )

    cover_text = (await engine.recognize_image(images[0])).strip()
    if not cover_text:
        raise ValueError("OCR returned empty text on capital verification report cover page")

    log_step(
        logger,
        task_id=task_id,
        registration_id=registration_id,
        step="ocr.capital.cover.done",
        message="验资报告首页 OCR 完成",
        page=1,
        textLength=len(cover_text),
    )

    detail = await _extract_cover_fields(
        cover_text,
        llm,
        task_id=task_id,
        registration_id=registration_id,
    )
    log_step(
        logger,
        task_id=task_id,
        registration_id=registration_id,
        step="capital.cover_only.done",
        message="验资报告首页抽取完成（未处理后续页）",
        detail={key: detail.get(key, "") for key in COVER_FIELD_KEYS},
    )
    return detail, cover_text
