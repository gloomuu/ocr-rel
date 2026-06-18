from __future__ import annotations

from typing import Any

from PIL import Image

from ocr_rel.config import settings
from ocr_rel.llm.client import LlmClient
from ocr_rel.llm.vision import model_supports_vision
from ocr_rel.llm.prompts import (
    AUDIT_COVER_FIELD_KEYS,
    CAPITAL_VERIFICATION_COVER_FIELD_KEYS,
    GRADE_PROTECTION_FIELD_KEYS,
    SOFTWARE_COPYRIGHT_FIELD_KEYS,
    build_audit_cover_system_prompt,
    build_audit_cover_user_prompt,
    build_balance_sheet_total_assets_system_prompt,
    build_balance_sheet_total_assets_user_prompt,
    build_business_license_register_authority_system_prompt,
    build_business_license_register_authority_user_prompt,
    build_business_license_seal_fields_system_prompt,
    build_business_license_seal_fields_user_prompt,
    build_capital_verification_cover_system_prompt,
    build_capital_verification_cover_user_prompt,
    build_grade_protection_system_prompt,
    build_grade_protection_user_prompt,
    build_software_copyright_system_prompt,
    build_software_copyright_user_prompt,
    build_system_prompt,
    build_user_prompt,
    get_field_schema,
)
from ocr_rel.llm.validator import _normalize_field, is_detail_sufficient, normalize_detail
from ocr_rel.logging_config import get_logger
from ocr_rel.parsers.registry import supported_types
from ocr_rel.parsers.text_utils import is_invalid_register_authority
from ocr_rel.parsers.type3_audit_report import is_invalid_accounting_firm_name

logger = get_logger(__name__)


class LlmExtractor:
    def __init__(self, client: LlmClient | None = None) -> None:
        self._client = client or LlmClient()

    @property
    def is_available(self) -> bool:
        return self._client.is_configured

    async def extract(
        self,
        doc_type: int,
        ocr_text: str,
        *,
        personnel: str | None = None,
        attachment_name: str | None = None,
    ) -> dict[str, Any]:
        if doc_type not in supported_types():
            raise ValueError(f"Document type {doc_type} is not supported for LLM extraction")

        system_prompt = build_system_prompt(doc_type)
        user_prompt = build_user_prompt(
            ocr_text,
            personnel=personnel,
            attachment_name=attachment_name if doc_type != 6 else None,
        )
        raw = await self._client.chat_json(system_prompt=system_prompt, user_prompt=user_prompt)
        detail = normalize_detail(doc_type, raw)

        if personnel and doc_type in {5, 9, 10}:
            detail["personnel"] = personnel

        if not is_detail_sufficient(doc_type, detail):
            raise ValueError("LLM extraction result is insufficient")

        return detail

    async def extract_grade_protection_fields(self, full_text: str) -> dict[str, str]:
        if not self.is_available:
            raise ValueError("LLM is not configured")

        if not full_text.strip():
            raise ValueError("Grade protection OCR text is empty")

        system_prompt = build_grade_protection_system_prompt()
        user_prompt = build_grade_protection_user_prompt(full_text)
        raw = await self._client.chat_json(system_prompt=system_prompt, user_prompt=user_prompt)

        detail: dict[str, str] = {}
        for key in GRADE_PROTECTION_FIELD_KEYS:
            value = raw.get(key, "")
            detail[key] = str(value).strip() if value is not None else ""

        for key, value in detail.items():
            detail[key] = _normalize_field(key, value)

        if not any(detail.values()):
            raise ValueError("LLM grade protection extraction result is empty")

        return detail

    async def extract_software_copyright_fields(self, cover_text: str) -> dict[str, str]:
        if not self.is_available:
            raise ValueError("LLM is not configured")

        if not cover_text.strip():
            raise ValueError("Software copyright OCR text is empty")

        system_prompt = build_software_copyright_system_prompt()
        user_prompt = build_software_copyright_user_prompt(cover_text)
        raw = await self._client.chat_json(system_prompt=system_prompt, user_prompt=user_prompt)

        value = raw.get("copyrightOwner", "")
        copyright_owner = _normalize_field("copyrightOwner", str(value).strip() if value is not None else "")
        if not copyright_owner:
            raise ValueError("LLM software copyright extraction result is empty")

        return {"copyrightOwner": copyright_owner}

    async def extract_total_assets(self, balance_sheet_text: str) -> str:
        if not self.is_available:
            raise ValueError("LLM is not configured")

        if not balance_sheet_text.strip():
            raise ValueError("Balance sheet OCR text is empty")

        system_prompt = build_balance_sheet_total_assets_system_prompt()
        user_prompt = build_balance_sheet_total_assets_user_prompt(balance_sheet_text)
        raw = await self._client.chat_json(system_prompt=system_prompt, user_prompt=user_prompt)
        value = raw.get("totalAssets", "")
        normalized = _normalize_field("totalAssets", str(value).strip())
        if not normalized:
            raise ValueError("LLM returned empty or invalid totalAssets")
        return normalized

    async def extract_cover_fields(self, cover_text: str) -> dict[str, str]:
        if not self.is_available:
            raise ValueError("LLM is not configured")

        if not cover_text.strip():
            raise ValueError("Cover OCR text is empty")

        system_prompt = build_audit_cover_system_prompt()
        user_prompt = build_audit_cover_user_prompt(cover_text)
        raw = await self._client.chat_json(system_prompt=system_prompt, user_prompt=user_prompt)

        detail: dict[str, str] = {}
        for key in AUDIT_COVER_FIELD_KEYS:
            value = raw.get(key, "")
            detail[key] = str(value).strip() if value is not None else ""

        if is_invalid_accounting_firm_name(detail.get("accountingFirmName", "")):
            detail["accountingFirmName"] = ""

        if not any(detail.values()):
            raise ValueError("LLM cover extraction result is empty")

        return detail

    async def extract_capital_verification_cover_fields(self, cover_text: str) -> dict[str, str]:
        if not self.is_available:
            raise ValueError("LLM is not configured")

        if not cover_text.strip():
            raise ValueError("Cover OCR text is empty")

        system_prompt = build_capital_verification_cover_system_prompt()
        user_prompt = build_capital_verification_cover_user_prompt(cover_text)
        raw = await self._client.chat_json(system_prompt=system_prompt, user_prompt=user_prompt)

        detail: dict[str, str] = {}
        for key in CAPITAL_VERIFICATION_COVER_FIELD_KEYS:
            value = raw.get(key, "")
            detail[key] = str(value).strip() if value is not None else ""

        if is_invalid_accounting_firm_name(detail.get("accountingFirmName", "")):
            detail["accountingFirmName"] = ""

        if not any(detail.values()):
            raise ValueError("LLM cover extraction result is empty")

        return detail

    async def extract_seal_fields(
        self,
        page_text: str,
        seal_text: str = "",
        *,
        seal_images: list[Image.Image] | None = None,
    ) -> dict[str, str]:
        if not self.is_available:
            raise ValueError("LLM is not configured")

        images = list(seal_images or [])
        if not images:
            raise ValueError("Seal images are required for multimodal seal extraction")
        if not model_supports_vision(settings.llm_model):
            raise ValueError(f"Model {settings.llm_model!r} does not support vision input")

        system_prompt = build_business_license_seal_fields_system_prompt()
        user_prompt = build_business_license_seal_fields_user_prompt(
            page_text,
            seal_text,
            has_seal_image=True,
        )

        raw = await self._client.chat_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            images=images,
        )
        logger.info(
            "LLM seal fields raw response (model=%s, images=%d): %s",
            settings.llm_model,
            len(images),
            raw,
        )

        authority = str(raw.get("registerAuthority", "")).strip()
        if is_invalid_register_authority(authority):
            authority = ""

        approval_date = _normalize_field("approvalDate", str(raw.get("approvalDate", "")).strip())

        normalized = {
            "registerAuthority": authority,
            "approvalDate": approval_date,
        }
        logger.info("LLM seal fields normalized: %s", normalized)
        return normalized

    async def extract_register_authority(self, page_text: str, seal_text: str = "") -> str:
        fields = await self.extract_seal_fields(page_text, seal_text)
        return fields["registerAuthority"]
