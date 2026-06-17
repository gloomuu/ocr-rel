from __future__ import annotations

from typing import Any

from PIL import Image

from ocr_rel.config import settings
from ocr_rel.llm.extractor import LlmExtractor
from ocr_rel.logging_config import get_logger, log_step
from ocr_rel.ocr.base import OcrEngine
from ocr_rel.parsers.type3_audit_report import (
    extract_cover_fields,
    extract_total_assets_from_balance_sheet,
    is_balance_sheet_page,
    is_invalid_accounting_firm_name,
)

logger = get_logger(__name__)

COVER_FIELD_KEYS = ("companyName", "accountingFirmName", "reportCode")


def _merge_cover_fields(llm_detail: dict[str, str], regex_detail: dict[str, str]) -> dict[str, str]:
    merged = dict(regex_detail)
    merged["totalAssets"] = ""

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
                step="llm.audit.cover.start",
                message="提交审计报告首页至大模型提取封面字段",
                textLength=len(cover_text),
            )
            llm_detail = await llm_extractor.extract_cover_fields(cover_text)
            detail = _merge_cover_fields(llm_detail, regex_detail)
            log_step(
                logger,
                task_id=task_id,
                registration_id=registration_id,
                step="llm.audit.cover.done",
                message="大模型已提取审计报告封面字段",
                detail={key: detail.get(key, "") for key in COVER_FIELD_KEYS},
            )
            return detail
        except Exception as exc:
            log_step(
                logger,
                task_id=task_id,
                registration_id=registration_id,
                step="llm.audit.cover.failed",
                message=str(exc),
            )
            if not settings.llm_fallback_to_regex:
                return regex_detail

    log_step(
        logger,
        task_id=task_id,
        registration_id=registration_id,
        step="regex.audit.cover.done",
        message="规则已提取审计报告封面字段",
        detail={key: regex_detail.get(key, "") for key in COVER_FIELD_KEYS},
    )
    return regex_detail


async def _extract_total_assets_from_page(
    page_text: str,
    llm_extractor: LlmExtractor,
    *,
    task_id: str | None = None,
    registration_id: str | None = None,
    page_number: int,
) -> str | None:
    if llm_extractor.is_available:
        try:
            assets = await llm_extractor.extract_total_assets(page_text)
            log_step(
                logger,
                task_id=task_id,
                registration_id=registration_id,
                step="llm.audit.total_assets.done",
                message="大模型已从资产负债表页提取 totalAssets",
                page=page_number,
                totalAssets=assets,
            )
            return assets
        except Exception as exc:
            log_step(
                logger,
                task_id=task_id,
                registration_id=registration_id,
                step="llm.audit.total_assets.failed",
                message=str(exc),
                page=page_number,
            )
            if not settings.llm_fallback_to_regex:
                return None

    assets = extract_total_assets_from_balance_sheet(page_text)
    if assets:
        log_step(
            logger,
            task_id=task_id,
            registration_id=registration_id,
            step="regex.audit.total_assets.done",
            message="规则已从资产负债表页提取 totalAssets",
            page=page_number,
            totalAssets=assets,
        )
    return assets


async def recognize_audit_report_detail(
    engine: OcrEngine,
    images: list[Image.Image],
    *,
    llm_extractor: LlmExtractor | None = None,
    task_id: str | None = None,
    registration_id: str | None = None,
) -> tuple[dict[str, Any], str]:
    """OCR audit report: cover fields and totalAssets via LLM, with regex fallback."""
    if not images:
        raise ValueError("Audit report PDF contains no pages")

    llm = llm_extractor or LlmExtractor()

    cover_text = (await engine.recognize_image(images[0])).strip()
    if not cover_text:
        raise ValueError("OCR returned empty text on audit report cover page")

    log_step(
        logger,
        task_id=task_id,
        registration_id=registration_id,
        step="ocr.audit.cover.done",
        message="审计报告首页 OCR 完成",
        page=1,
        textLength=len(cover_text),
    )

    detail = await _extract_cover_fields(
        cover_text,
        llm,
        task_id=task_id,
        registration_id=registration_id,
    )

    for page_number, image in enumerate(images[1:], start=2):
        page_text = (await engine.recognize_image(image)).strip()
        if not page_text:
            log_step(
                logger,
                task_id=task_id,
                registration_id=registration_id,
                step="ocr.audit.page.empty",
                message="审计报告页面 OCR 为空，跳过",
                page=page_number,
            )
            continue

        is_balance_sheet = is_balance_sheet_page(page_text)
        log_step(
            logger,
            task_id=task_id,
            registration_id=registration_id,
            step="ocr.audit.page.done",
            message="审计报告分页 OCR 完成",
            page=page_number,
            textLength=len(page_text),
            isBalanceSheet=is_balance_sheet,
        )

        if not is_balance_sheet:
            continue

        log_step(
            logger,
            task_id=task_id,
            registration_id=registration_id,
            step="llm.audit.total_assets.start",
            message="提交资产负债表页至大模型提取 totalAssets",
            page=page_number,
            textLength=len(page_text),
        )

        assets = await _extract_total_assets_from_page(
            page_text,
            llm,
            task_id=task_id,
            registration_id=registration_id,
            page_number=page_number,
        )
        if assets:
            detail["totalAssets"] = assets
            log_step(
                logger,
                task_id=task_id,
                registration_id=registration_id,
                step="ocr.audit.balance_sheet.found",
                message="已定位资产负债表并提取资产总计",
                page=page_number,
                totalAssets=assets,
            )
            break

        log_step(
            logger,
            task_id=task_id,
            registration_id=registration_id,
            step="ocr.audit.balance_sheet.missed",
            message="页面含资产负债表特征但未提取到有效 totalAssets，继续扫描",
            page=page_number,
        )

    return detail, cover_text
