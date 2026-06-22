from __future__ import annotations

import re
from typing import Any

from ocr_rel.parsers.base import BaseParser
from ocr_rel.parsers.text_utils import contains_keyword
from ocr_rel.parsers.type2_legal_person_id import LegalPersonIdParser

_CREDIT_REPORT_MARKERS: tuple[str, ...] = (
    "个人信用报告",
    "中国人民银行征信中心",
    "征信中心",
    "征信报告",
    "信用报告",
    "被查询者姓名",
    "被查询者证件号码",
    "信息概要",
    "信贷记录",
)

_NAME_PATTERNS: tuple[str, ...] = (
    r"被查询者姓名[:：]?\s*([\u4e00-\u9fff·]{2,10})",
    r"查询者姓名[:：]?\s*([\u4e00-\u9fff·]{2,10})",
    r"姓名[:：]?\s*([\u4e00-\u9fff·]{2,10})",
)

_ID_CARD_PATTERNS: tuple[str, ...] = (
    r"被查询者证件号码[:：]?\s*(\d{17}[\dXx])",
    r"证件号码[:：]?\s*(\d{17}[\dXx])",
    r"身份证号码[:：]?\s*(\d{17}[\dXx])",
    r"公民身份号码[:：]?\s*(\d{17}[\dXx])",
)


def is_credit_report_content(text: str) -> bool:
    if not text.strip():
        return False
    hits = sum(1 for marker in _CREDIT_REPORT_MARKERS if contains_keyword(text, marker))
    return hits >= 2 or contains_keyword(text, "个人信用报告")


class CreditReportParser(BaseParser):
    doc_type = 7

    def __init__(self) -> None:
        self._id_parser = LegalPersonIdParser()

    def parse(
        self,
        text: str,
        personnel: str | None = None,
        attachment_name: str | None = None,
    ) -> dict[str, Any]:
        del personnel, attachment_name
        compact = self._normalize(text)
        name = self._extract_queried_name(text, compact)
        id_card = self._extract_id_card(text, compact)

        if not name or not id_card:
            fallback = self._id_parser.parse(text)
            name = name or fallback.get("name", "")
            id_card = id_card or fallback.get("idCardNumber", "")

        return {
            "name": name or "",
            "idCardNumber": id_card or "",
        }

    def _extract_queried_name(self, text: str, compact: str) -> str | None:
        for pattern in _NAME_PATTERNS:
            match = re.search(pattern, text)
            if match:
                return match.group(1).strip()
        for pattern in _NAME_PATTERNS:
            compact_pattern = pattern.replace(r"\s*", "")
            match = re.search(compact_pattern, compact)
            if match:
                return match.group(1).strip()
        return None

    def _extract_id_card(self, text: str, compact: str) -> str | None:
        for pattern in _ID_CARD_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).upper()
        for pattern in _ID_CARD_PATTERNS:
            compact_pattern = pattern.replace(r"\s*", "")
            match = re.search(compact_pattern, compact, re.IGNORECASE)
            if match:
                return match.group(1).upper()
        match = re.search(r"(\d{17}[\dXx])", compact)
        if match:
            return match.group(1).upper()
        return None
