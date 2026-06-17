from __future__ import annotations

from typing import Any

from ocr_rel.config import settings
from ocr_rel.llm.extractor import LlmExtractor
from ocr_rel.logging_config import get_logger, log_step
from ocr_rel.parsers.registry import get_parser, supported_types
from ocr_rel.parsers.text_utils import extract_register_authority, is_invalid_register_authority
from ocr_rel.parsers.type3_audit_report import extract_total_assets

logger = get_logger(__name__)


class ExtractionService:
    def __init__(self, llm_extractor: LlmExtractor | None = None) -> None:
        self._llm_extractor = llm_extractor or LlmExtractor()

    @staticmethod
    def _finalize_business_license_detail(detail: dict[str, Any], ocr_text: str) -> dict[str, Any]:
        authority = extract_register_authority(ocr_text)
        if authority:
            detail["registerAuthority"] = authority
        elif is_invalid_register_authority(str(detail.get("registerAuthority", ""))):
            detail["registerAuthority"] = ""
        return detail

    @staticmethod
    def _finalize_audit_report_detail(detail: dict[str, Any], ocr_text: str) -> dict[str, Any]:
        assets = extract_total_assets(ocr_text)
        if assets:
            detail["totalAssets"] = assets
        return detail

    async def extract(
        self,
        doc_type: int,
        ocr_text: str,
        *,
        personnel: str | None = None,
        task_id: str | None = None,
        registration_id: str | None = None,
    ) -> dict[str, Any]:
        if doc_type not in supported_types():
            raise ValueError(f"Document type {doc_type} is not supported yet")

        strategy = settings.extraction_strategy.lower()
        use_llm = strategy == "llm" and self._llm_extractor.is_available

        if use_llm:
            try:
                log_step(
                    logger,
                    task_id=task_id,
                    registration_id=registration_id,
                    step="llm.extract.start",
                    message="调用大模型结构化抽取",
                    docType=doc_type,
                    model=settings.llm_model,
                )
                detail = await self._llm_extractor.extract(
                    doc_type,
                    ocr_text,
                    personnel=personnel,
                )
                log_step(
                    logger,
                    task_id=task_id,
                    registration_id=registration_id,
                    step="llm.extract.done",
                    message="大模型抽取成功",
                    docType=doc_type,
                )
                if doc_type == 1:
                    detail = self._finalize_business_license_detail(detail, ocr_text)
                elif doc_type == 3:
                    detail = self._finalize_audit_report_detail(detail, ocr_text)
                return detail
            except Exception as exc:
                log_step(
                    logger,
                    task_id=task_id,
                    registration_id=registration_id,
                    step="llm.extract.failed",
                    message=str(exc),
                    docType=doc_type,
                )
                if not settings.llm_fallback_to_regex:
                    raise

        log_step(
            logger,
            task_id=task_id,
            registration_id=registration_id,
            step="regex.extract.start",
            message="使用 regex 规则抽取",
            docType=doc_type,
        )
        detail = get_parser(doc_type).parse(ocr_text, personnel=personnel)
        if doc_type == 1:
            detail = self._finalize_business_license_detail(detail, ocr_text)
        elif doc_type == 3:
            detail = self._finalize_audit_report_detail(detail, ocr_text)
        log_step(
            logger,
            task_id=task_id,
            registration_id=registration_id,
            step="regex.extract.done",
            message="regex 抽取完成",
            docType=doc_type,
        )
        return detail


extraction_service = ExtractionService()
