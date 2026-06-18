from __future__ import annotations

import re
from typing import Any

from ocr_rel.parsers.base import BaseParser
from ocr_rel.parsers.text_utils import extract_company_name, extract_labeled_field
from ocr_rel.parsers.type3_audit_report import (
    REPORT_CODE_INLINE_PATTERN,
    extract_accounting_firm_name,
    extract_report_code as extract_audit_report_code,
)

COMPANY_LABELS = [
    "被验资单位",
    "验资单位",
    "单位名称",
    "公司名称",
    "企业名称",
    "委托单位",
]

REPORT_CODE_LABELS = [
    "验资报告文号",
    "报告文号",
    "报告编号",
    "报告编码",
    "文号",
]

CAPITAL_VERIFICATION_REPORT_NO_PATTERN = re.compile(
    r"([\u4e00-\u9fff]{2,10}验字[\(（]?\d{4}[\)）]?第[A-Za-z0-9]+号)"
)
REPORT_CODE_PATTERN = re.compile(
    r"([\u4e00-\u9fff0-9A-Za-z（）()\[\]【】〔〕\-—_·]{6,40}"
    r"(?:号|字|验|报|第[\d]+号))"
)


def extract_capital_verification_company_name(text: str) -> str | None:
    labeled = extract_labeled_field(text, COMPANY_LABELS)
    if labeled and len(labeled) >= 4:
        cleaned = _trim_company_noise(labeled)
        if cleaned and "会计师事务所" not in cleaned:
            return cleaned

    match = re.search(
        r"(?:被验资单位|验资单位)[:：]?\s*([\u4e00-\u9fff（）()·]{4,60}"
        r"(?:有限责任公司|股份有限公司|有限公司|集团有限公司|公司|企业))",
        text,
    )
    if match:
        return _trim_company_noise(match.group(1))

    company = extract_company_name(text)
    if company and "会计师事务所" not in company:
        return company
    return None


def extract_capital_verification_report_code(text: str) -> str | None:
    flattened = text.replace("\n", " ")

    inline_encoding = REPORT_CODE_INLINE_PATTERN.search(flattened)
    if inline_encoding:
        return _clean_report_code(inline_encoding.group(1))

    labeled = extract_labeled_field(text, REPORT_CODE_LABELS)
    if labeled:
        cleaned = _clean_report_code(labeled)
        if len(cleaned) >= 4:
            return cleaned

    verification_no_match = CAPITAL_VERIFICATION_REPORT_NO_PATTERN.search(
        flattened.replace(" ", "")
    )
    if verification_no_match:
        return verification_no_match.group(1).strip()

    audit_code = extract_audit_report_code(text)
    if audit_code:
        return audit_code

    match = REPORT_CODE_PATTERN.search(flattened)
    if match:
        return match.group(1).strip()
    return None


def extract_cover_fields(text: str) -> dict[str, str]:
    return {
        "companyName": extract_capital_verification_company_name(text) or "",
        "accountingFirmName": extract_accounting_firm_name(text) or "",
        "reportCode": extract_capital_verification_report_code(text) or "",
    }


def _clean_report_code(value: str) -> str:
    return value.strip(" ：:;；,.，。()（）")


def _trim_company_noise(value: str) -> str:
    trimmed = value.strip(" ：:;；,.，。")
    for marker in ("会计师事务所", "验资机构", "报告文号", "报告编码", "注册资本", "实收资本"):
        index = trimmed.find(marker)
        if index > 0:
            trimmed = trimmed[:index]
    return trimmed.strip(" ：:;；,.，。")


class CapitalVerificationParser(BaseParser):
    doc_type = 4

    def parse(
        self,
        text: str,
        personnel: str | None = None,
        attachment_name: str | None = None,
    ) -> dict[str, Any]:
        return extract_cover_fields(text)
