from __future__ import annotations

from typing import Any

from ocr_rel.llm.client import LlmClient
from ocr_rel.llm.prompts import (
    AUDIT_COVER_FIELD_KEYS,
    build_audit_cover_system_prompt,
    build_audit_cover_user_prompt,
    build_balance_sheet_total_assets_system_prompt,
    build_balance_sheet_total_assets_user_prompt,
    build_system_prompt,
    build_user_prompt,
    get_field_schema,
)
from ocr_rel.llm.validator import _normalize_field, is_detail_sufficient, normalize_detail
from ocr_rel.parsers.type3_audit_report import is_invalid_accounting_firm_name
from ocr_rel.logging_config import get_logger
from ocr_rel.parsers.registry import supported_types

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
    ) -> dict[str, Any]:
        if doc_type not in supported_types():
            raise ValueError(f"Document type {doc_type} is not supported for LLM extraction")

        system_prompt = build_system_prompt(doc_type)
        user_prompt = build_user_prompt(ocr_text, personnel=personnel)
        raw = await self._client.chat_json(system_prompt=system_prompt, user_prompt=user_prompt)
        detail = normalize_detail(doc_type, raw)

        if personnel and doc_type in {5, 9, 10}:
            detail["personnel"] = personnel

        if not is_detail_sufficient(doc_type, detail):
            raise ValueError("LLM extraction result is insufficient")

        return detail

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
