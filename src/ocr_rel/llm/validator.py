from __future__ import annotations

import re
from typing import Any

from ocr_rel.llm.prompts import get_field_schema
from ocr_rel.parsers.text_utils import format_chinese_date
from ocr_rel.parsers.type3_audit_report import normalize_total_assets_yuan
from ocr_rel.parsers.type6_grade_protection import normalize_system_level

CREDIT_CODE_PATTERN = re.compile(r"^[0-9A-Z]{18}$")
ID_CARD_PATTERN = re.compile(r"^\d{17}[\dXx]$")
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def normalize_detail(doc_type: int, raw: dict[str, Any]) -> dict[str, str]:
    schema = get_field_schema(doc_type)
    normalized: dict[str, str] = {}

    for key in schema:
        value = raw.get(key, "")
        if value is None:
            normalized[key] = ""
            continue
        normalized[key] = _normalize_field(key, str(value).strip())

    return normalized


def _normalize_field(key: str, value: str) -> str:
    if not value:
        return ""

    if key in {"establishDate", "approvalDate"}:
        return _normalize_date(value)

    if key == "unifiedSocialCreditCode":
        compact = re.sub(r"\s+", "", value.upper())
        return compact if CREDIT_CODE_PATTERN.match(compact) else ""

    if key == "idCardNumber":
        compact = re.sub(r"\s+", "", value.upper())
        return compact if ID_CARD_PATTERN.match(compact) else ""

    if key == "totalAssets":
        return _normalize_total_assets(value)

    if key == "systemLevel":
        return normalize_system_level(value)

    return value


def _normalize_total_assets(value: str) -> str:
    if not value:
        return ""
    wan_unit = "万" in value and "亿" not in value
    normalized = normalize_total_assets_yuan(value, wan_unit=wan_unit)
    return normalized or ""


def _normalize_date(value: str) -> str:
    if DATE_PATTERN.match(value):
        return value
    if re.search(r"\d{4}[年\-/\.]", value):
        return format_chinese_date(value)
    return ""


def is_detail_sufficient(doc_type: int, detail: dict[str, str]) -> bool:
    if doc_type == 1:
        return bool(detail.get("unifiedSocialCreditCode") or detail.get("companyName"))
    if doc_type in {2, 5}:
        return bool(detail.get("name") or detail.get("idCardNumber"))
    if doc_type == 3:
        return bool(detail.get("companyName") or detail.get("totalAssets") or detail.get("reportCode"))
    if doc_type == 4:
        return bool(detail.get("companyName") or detail.get("reportCode"))
    if doc_type == 6:
        return bool(
            detail.get("copyrightOwner")
            or detail.get("companyName")
            or detail.get("systemLevel")
        )
    return any(value for value in detail.values())
