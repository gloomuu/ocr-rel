from __future__ import annotations

import re

from ocr_rel.models.schemas import ATTACHMENT_TYPE_NAMES
from ocr_rel.parsers.registry import supported_types

_BUSINESS_LICENSE_KEYWORDS: list[tuple[str, int]] = [
    ("营业执照", 4),
    ("统一社会信用代码", 4),
    ("登记机关", 2),
    ("注册资本", 2),
    ("有限责任公司", 2),
    ("股份有限公司", 2),
    ("类型", 1),
    ("成立日期", 1),
    ("核准日期", 1),
    ("住所", 1),
]

_ID_CARD_KEYWORDS: list[tuple[str, int]] = [
    ("居民身份证", 4),
    ("公民身份号码", 4),
    ("身份号码", 3),
    ("签发机关", 2),
    ("有效期限", 2),
    ("性别", 1),
    ("民族", 1),
    ("出生", 1),
    ("住址", 1),
]

_AUDIT_REPORT_KEYWORDS: list[tuple[str, int]] = [
    ("审计报告", 4),
    ("会计师事务所", 3),
    ("被审计单位", 3),
    ("资产总额", 2),
    ("资产负债表", 2),
    ("审计意见", 2),
    ("报告文号", 2),
    ("报告编码", 2),
    ("报告编号", 2),
    ("资产总计", 2),
]

_TYPE_KEYWORDS: dict[int, list[tuple[str, int]]] = {
    1: _BUSINESS_LICENSE_KEYWORDS,
    2: _ID_CARD_KEYWORDS,
    3: _AUDIT_REPORT_KEYWORDS,
}

_CREDIT_CODE_PATTERN = re.compile(r"[0-9A-HJ-NP-RTUW-Y]{2}\d{6}[0-9A-HJ-NP-RTUW-Y]{10}")
_ID_CARD_PATTERN = re.compile(r"\d{17}[\dXx]")


class DocumentTypeMismatchError(ValueError):
    """Raised when OCR content does not match the declared document type."""


def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _keyword_score(text: str, keywords: list[tuple[str, int]]) -> int:
    score = 0
    for keyword, weight in keywords:
        if keyword in text:
            score += weight
    return score


def score_document_type(doc_type: int, text: str) -> int:
    if doc_type not in _TYPE_KEYWORDS:
        return 0

    normalized = _normalize(text)
    score = _keyword_score(text, _TYPE_KEYWORDS[doc_type]) + _keyword_score(
        normalized, _TYPE_KEYWORDS[doc_type]
    )

    if doc_type == 1 and _CREDIT_CODE_PATTERN.search(normalized):
        score += 3
    if doc_type == 2 and _ID_CARD_PATTERN.search(normalized):
        score += 3

    return score


def detect_document_type(text: str) -> int | None:
    scores = {doc_type: score_document_type(doc_type, text) for doc_type in supported_types()}
    if not scores:
        return None

    best_type, best_score = max(scores.items(), key=lambda item: item[1])
    if best_score < 3:
        return None
    return best_type


def validate_document_type(doc_type: int, text: str) -> None:
    """Validate OCR text matches declared attachment type; raise on mismatch."""
    if doc_type not in supported_types():
        return

    declared_name = ATTACHMENT_TYPE_NAMES.get(doc_type, f"type-{doc_type}")
    declared_score = score_document_type(doc_type, text)
    detected_type = detect_document_type(text)

    if detected_type is not None and detected_type != doc_type:
        detected_name = ATTACHMENT_TYPE_NAMES.get(detected_type, f"type-{detected_type}")
        raise DocumentTypeMismatchError(
            f"文件内容与声明类型不一致：声明为「{declared_name}」，"
            f"识别内容更符合「{detected_name}」"
        )

    if declared_score < 3:
        raise DocumentTypeMismatchError(
            f"文件内容与声明类型不一致：无法从识别内容确认该文件为「{declared_name}」"
        )
