from __future__ import annotations

import re
from typing import Any

from ocr_rel.parsers.base import BaseParser
from ocr_rel.parsers.text_utils import COMPANY_NAME_PATTERN, contains_keyword

_CREDIT_PROOF_MARKERS: tuple[str, ...] = (
    "中国执行信息公开网",
    "失信被执行人",
    "全国法院失信被执行人",
    "被执行人",
    "查询结果",
    "执行信息公开",
    "信用中国",
    "严重违法失信",
    "失信被执行",
)

_NAME_PATTERNS: tuple[str, ...] = (
    r"被执行人姓名/名称[:：]?\s*([\u4e00-\u9fff·（）()A-Za-z0-9]{2,60})",
    r"被执行人姓名[:：]?\s*([\u4e00-\u9fff·（）()A-Za-z0-9]{2,60})",
    r"被执行人名称[:：]?\s*([\u4e00-\u9fff·（）()A-Za-z0-9]{2,60})",
    r"姓名[:：]?\s*([\u4e00-\u9fff·]{2,10})",
    r"名称[:：]?\s*([\u4e00-\u9fff·（）()A-Za-z0-9]{2,60})",
    r"企业名称[:：]?\s*([\u4e00-\u9fff·（）()A-Za-z0-9]{2,60})",
)

_QUERY_RESULT_PATTERNS: tuple[str, ...] = (
    r"查询结果[:：]?\s*([^\n]{2,120})",
    r"查询到\s*(\d+\s*条[^\n]{0,40})",
    r"(在全国范围内没有找到[^\n]{0,40})",
    r"(没有找到[^\n]{0,40})",
    r"(暂无[^\n]{0,40})",
)

_QUERY_RESULT_STOP_WORDS = (
    "证件号码",
    "组织机构代码",
    "被执行人",
    "验证码",
    "查询条件",
)

STANDARD_NO_DISHONESTY_RESULT = "暂无失信记录"

_NO_DISHONESTY_OCR_MARKERS: tuple[str, ...] = (
    "在全国范围内没有找到",
    "全国范围内未找到",
    "没有找到符合条件",
    "没有找到相关的结果",
    "没有找到相关",
    "未查询到",
    "未查到",
    "无相关记录",
    "无符合条件的",
    "不存在失信",
    "无失信记录",
    "暂无失信",
)

_NO_DISHONESTY_COMPACT_PATTERNS: tuple[str, ...] = (
    r"共查询到0条",
    r"查询到0条",
    r"0条记录",
    r"0条相关",
)

_HAS_DISHONESTY_COMPACT_PATTERNS: tuple[str, ...] = (
    r"共查询到[1-9]\d*条",
    r"查询到[1-9]\d*条",
    r"共[1-9]\d*条",
)

_HAS_DISHONESTY_OCR_MARKERS: tuple[str, ...] = (
    "限制消费令",
    "被列入失信",
    "存在失信",
    "有失信记录",
    "失信信息",
)


def ocr_indicates_dishonesty(text: str) -> bool:
    compact = re.sub(r"\s+", "", text)
    for marker in _HAS_DISHONESTY_OCR_MARKERS:
        if contains_keyword(text, marker):
            return True
    return any(re.search(pattern, compact) for pattern in _HAS_DISHONESTY_COMPACT_PATTERNS)


def ocr_indicates_no_dishonesty(text: str) -> bool:
    if ocr_indicates_dishonesty(text):
        return False

    compact = re.sub(r"\s+", "", text)
    for marker in _NO_DISHONESTY_OCR_MARKERS:
        if contains_keyword(text, marker):
            return True
    return any(re.search(pattern, compact) for pattern in _NO_DISHONESTY_COMPACT_PATTERNS)


def finalize_credit_proof_detail(detail: dict[str, Any], ocr_text: str) -> dict[str, Any]:
    """Infer queryResult from OCR when the queried subject has no dishonesty records."""
    merged = dict(detail)
    if ocr_indicates_no_dishonesty(ocr_text):
        merged["queryResult"] = STANDARD_NO_DISHONESTY_RESULT
    return merged


def is_credit_proof_content(text: str) -> bool:
    if not text.strip():
        return False
    hits = sum(1 for marker in _CREDIT_PROOF_MARKERS if contains_keyword(text, marker))
    return hits >= 2 or contains_keyword(text, "失信被执行人")


def _clean_name(value: str) -> str:
    cleaned = value.strip().strip("：:，,;；")
    cleaned = re.sub(r"(证件号码|组织机构代码|查询结果).*$", "", cleaned).strip()
    return cleaned


def _clean_query_result(value: str) -> str:
    cleaned = value.strip().strip("：:，,;；.")
    for stop in _QUERY_RESULT_STOP_WORDS:
        index = cleaned.find(stop)
        if index > 0:
            cleaned = cleaned[:index].strip()
    return cleaned


class CreditProofParser(BaseParser):
    doc_type = 8

    def parse(
        self,
        text: str,
        personnel: str | None = None,
        attachment_name: str | None = None,
    ) -> dict[str, Any]:
        del personnel, attachment_name
        compact = self._normalize(text)
        name = self._extract_executed_person_name(text, compact)
        query_result = self._extract_query_result(text, compact)

        return finalize_credit_proof_detail(
            {
                "executedPersonName": name or "",
                "queryResult": query_result or "",
            },
            text,
        )

    def _extract_executed_person_name(self, text: str, compact: str) -> str | None:
        for pattern in _NAME_PATTERNS:
            match = re.search(pattern, text)
            if match:
                cleaned = _clean_name(match.group(1))
                if cleaned:
                    return cleaned

        for pattern in _NAME_PATTERNS:
            compact_pattern = pattern.replace(r"\s*", "")
            match = re.search(compact_pattern, compact)
            if match:
                cleaned = _clean_name(match.group(1))
                if cleaned:
                    return cleaned

        company_match = COMPANY_NAME_PATTERN.search(text)
        if company_match and contains_keyword(text, "被执行人"):
            return company_match.group(1).strip()

        return None

    def _extract_query_result(self, text: str, compact: str) -> str | None:
        for pattern in _QUERY_RESULT_PATTERNS:
            match = re.search(pattern, text)
            if match:
                cleaned = _clean_query_result(match.group(1))
                if cleaned:
                    return cleaned

        for pattern in _QUERY_RESULT_PATTERNS:
            compact_pattern = pattern.replace(r"\s*", "")
            match = re.search(compact_pattern, compact)
            if match:
                cleaned = _clean_query_result(match.group(1))
                if cleaned:
                    return cleaned

        return None
