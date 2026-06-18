from __future__ import annotations

from typing import Any

from PIL import Image

from ocr_rel.config import settings
from ocr_rel.llm.extractor import LlmExtractor
from ocr_rel.logging_config import get_logger, log_step
from ocr_rel.ocr.base import OcrEngine
from ocr_rel.ocr.service import BusinessLicenseOcrResult, recognize_business_license_ocr
from ocr_rel.llm.vision import model_supports_vision
from ocr_rel.parsers.text_utils import (
    extract_approval_date,
    extract_approval_date_from_seal,
    extract_register_authority,
    is_invalid_register_authority,
)
from ocr_rel.parsers.type1_business_license import BusinessLicenseParser

logger = get_logger(__name__)


def _merge_register_authority(regex_value: str, llm_value: str) -> str:
    """OCR/regex first; LLM supplements when OCR is empty or invalid."""
    regex_value = regex_value.strip()
    llm_value = llm_value.strip()
    if regex_value and not is_invalid_register_authority(regex_value):
        return regex_value
    if llm_value and not is_invalid_register_authority(llm_value):
        return llm_value
    return ""


def _merge_approval_date(
    regex_value: str,
    llm_value: str,
    *,
    establish_date: str,
) -> str:
    """OCR/regex first; LLM supplements when OCR is empty."""
    regex_value = regex_value.strip()
    llm_value = llm_value.strip()
    if regex_value and regex_value != establish_date:
        return regex_value
    if llm_value and llm_value != establish_date:
        return llm_value
    return ""


def _regex_seal_fields(ocr_result: BusinessLicenseOcrResult, establish_date: str) -> dict[str, str]:
    authority = (
        extract_register_authority(ocr_result.seal_text)
        or extract_register_authority(ocr_result.combined_text)
        or ""
    )
    approval_date = (
        extract_approval_date_from_seal(ocr_result.seal_text, establish_date or None)
        or extract_approval_date(ocr_result.combined_text, establish_date or None)
        or ""
    )
    return {
        "registerAuthority": authority if not is_invalid_register_authority(authority) else "",
        "approvalDate": approval_date,
    }


async def _extract_seal_fields(
    ocr_result: BusinessLicenseOcrResult,
    llm_extractor: LlmExtractor,
    *,
    establish_date: str,
    task_id: str | None = None,
    registration_id: str | None = None,
) -> dict[str, str]:
    regex_fields = _regex_seal_fields(ocr_result, establish_date)
    log_step(
        logger,
        task_id=task_id,
        registration_id=registration_id,
        step="regex.business_license.seal",
        message="规则已提取营业执照公章区域字段",
        registerAuthority=regex_fields["registerAuthority"],
        approvalDate=regex_fields["approvalDate"],
    )

    if llm_extractor.is_available and ocr_result.seal_images and model_supports_vision(settings.llm_model):
        try:
            log_step(
                logger,
                task_id=task_id,
                registration_id=registration_id,
                step="llm.business_license.seal.start",
                message="提交营业执照公章区域图片至多模态大模型识别 registerAuthority / approvalDate",
                pageTextLength=len(ocr_result.page_text),
                sealTextLength=len(ocr_result.seal_text),
                sealImageCount=len(ocr_result.seal_images),
                llmModel=settings.llm_model,
            )
            llm_fields = await llm_extractor.extract_seal_fields(
                ocr_result.page_text,
                ocr_result.seal_text,
                seal_images=list(ocr_result.seal_images),
            )
            log_step(
                logger,
                task_id=task_id,
                registration_id=registration_id,
                step="llm.business_license.seal.raw",
                message="多模态大模型识别结果（公章区域字段）",
                llmRegisterAuthority=llm_fields.get("registerAuthority", ""),
                llmApprovalDate=llm_fields.get("approvalDate", ""),
            )
            merged = {
                "registerAuthority": _merge_register_authority(
                    regex_fields["registerAuthority"],
                    llm_fields.get("registerAuthority", ""),
                ),
                "approvalDate": _merge_approval_date(
                    regex_fields["approvalDate"],
                    llm_fields.get("approvalDate", ""),
                    establish_date=establish_date,
                ),
            }
            log_step(
                logger,
                task_id=task_id,
                registration_id=registration_id,
                step="llm.business_license.seal.done",
                message="营业执照公章区域字段合并完成（OCR 优先，多模态大模型补充）",
                ocrRegisterAuthority=regex_fields["registerAuthority"],
                ocrApprovalDate=regex_fields["approvalDate"],
                llmRegisterAuthority=llm_fields.get("registerAuthority", ""),
                llmApprovalDate=llm_fields.get("approvalDate", ""),
                registerAuthority=merged["registerAuthority"],
                approvalDate=merged["approvalDate"],
            )
            return merged
        except Exception as exc:
            log_step(
                logger,
                task_id=task_id,
                registration_id=registration_id,
                step="llm.business_license.seal.failed",
                message=str(exc),
            )
            if not settings.llm_fallback_to_regex:
                return regex_fields

    elif llm_extractor.is_available and not model_supports_vision(settings.llm_model):
        log_step(
            logger,
            task_id=task_id,
            registration_id=registration_id,
            step="llm.business_license.seal.skipped",
            message="当前模型不支持多模态读图，公章字段仅使用 OCR/规则结果，不做推测",
            llmModel=settings.llm_model,
            registerAuthority=regex_fields["registerAuthority"],
            approvalDate=regex_fields["approvalDate"],
        )

    return regex_fields


async def recognize_business_license_detail(
    engine: OcrEngine,
    images: list[Image.Image],
    *,
    llm_extractor: LlmExtractor | None = None,
    task_id: str | None = None,
    registration_id: str | None = None,
) -> tuple[dict[str, Any], str]:
    """OCR business license: regex for printed fields, LLM infers seal fields when OCR is missing."""
    if not images:
        raise ValueError("Business license image is empty")

    llm = llm_extractor or LlmExtractor()
    ocr_result = await recognize_business_license_ocr(engine, images)
    if not ocr_result.combined_text.strip():
        raise ValueError("OCR returned empty text")

    log_step(
        logger,
        task_id=task_id,
        registration_id=registration_id,
        step="ocr.business_license.done",
        message="营业执照 OCR 完成（全文 + 公章区域）",
        pageTextLength=len(ocr_result.page_text),
        sealTextLength=len(ocr_result.seal_text),
        pageTextPreview=ocr_result.page_text[:300],
        sealTextPreview=ocr_result.seal_text[:200],
    )

    detail = BusinessLicenseParser().parse(ocr_result.combined_text)
    seal_fields = await _extract_seal_fields(
        ocr_result,
        llm,
        establish_date=str(detail.get("establishDate", "")),
        task_id=task_id,
        registration_id=registration_id,
    )
    detail["registerAuthority"] = seal_fields["registerAuthority"]
    if seal_fields["approvalDate"]:
        detail["approvalDate"] = seal_fields["approvalDate"]
    return detail, ocr_result.combined_text
