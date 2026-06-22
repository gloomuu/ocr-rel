from __future__ import annotations

import re

from ocr_rel.models.schemas import ATTACHMENT_TYPE_NAMES
from ocr_rel.parsers.registry import supported_types
from ocr_rel.parsers.text_utils import contains_keyword

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

_CAPITAL_VERIFICATION_KEYWORDS: list[tuple[str, int]] = [
    ("验资报告", 4),
    ("被验资单位", 3),
    ("验资单位", 3),
    ("会计师事务所", 3),
    ("注册资本", 2),
    ("实收资本", 2),
    ("出资", 2),
    ("报告文号", 2),
    ("报告编码", 2),
    ("验字", 2),
]

_GRADE_PROTECTION_KEYWORDS: list[tuple[str, int]] = [
    ("信息系统安全等级", 5),
    ("网络安全等级保护", 5),
    ("信息安全等级保护", 5),
    ("等级保护备案证明", 5),
    ("等级保护", 4),
    ("等保", 3),
    ("备案证明", 3),
    ("安全保护等级", 3),
    ("公安机关", 2),
    ("备案号", 2),
    ("备案单位", 2),
    ("系统名称", 1),
    ("单位名称", 1),
]

_SOFTWARE_COPYRIGHT_KEYWORDS: list[tuple[str, int]] = [
    ("软件著作权", 5),
    ("软件著作权登记证书", 5),
    ("计算机软件著作权", 4),
    ("著作权登记", 3),
    ("著作权人", 3),
    ("登记号", 2),
    ("软件名称", 1),
]

_CREDIT_REPORT_KEYWORDS: list[tuple[str, int]] = [
    ("个人信用报告", 5),
    ("中国人民银行征信中心", 5),
    ("征信中心", 4),
    ("征信报告", 4),
    ("被查询者姓名", 3),
    ("被查询者证件号码", 3),
    ("信息概要", 2),
    ("信贷记录", 2),
    ("报告编号", 2),
    ("本人版", 1),
]

_CREDIT_PROOF_KEYWORDS: list[tuple[str, int]] = [
    ("中国执行信息公开网", 5),
    ("失信被执行人", 5),
    ("全国法院失信被执行人", 5),
    ("执行信息公开", 4),
    ("被执行人", 4),
    ("查询结果", 3),
    ("严重违法失信", 3),
    ("信用中国", 2),
    ("失信被执行", 2),
    ("证件号码", 1),
    ("组织机构代码", 1),
]

_TYPE6_KEYWORDS: list[tuple[str, int]] = _GRADE_PROTECTION_KEYWORDS + _SOFTWARE_COPYRIGHT_KEYWORDS

_TYPE_KEYWORDS: dict[int, list[tuple[str, int]]] = {
    1: _BUSINESS_LICENSE_KEYWORDS,
    2: _ID_CARD_KEYWORDS,
    3: _AUDIT_REPORT_KEYWORDS,
    4: _CAPITAL_VERIFICATION_KEYWORDS,
    5: _ID_CARD_KEYWORDS,
    6: _TYPE6_KEYWORDS,
    7: _CREDIT_REPORT_KEYWORDS,
    8: _CREDIT_PROOF_KEYWORDS,
    9: _CREDIT_PROOF_KEYWORDS,
    10: _CREDIT_PROOF_KEYWORDS,
    11: _CREDIT_PROOF_KEYWORDS,
}

_ID_CARD_TYPES = {2, 5}
_ID_PATTERN_TYPES = {2, 5, 7}

_CREDIT_CODE_PATTERN = re.compile(r"[0-9A-HJ-NP-RTUW-Y]{2}\d{6}[0-9A-HJ-NP-RTUW-Y]{10}")
_ID_CARD_PATTERN = re.compile(r"\d{17}[\dXx]")


class DocumentTypeMismatchError(ValueError):
    """Raised when OCR content does not match the declared document type."""


def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _keyword_score(text: str, keywords: list[tuple[str, int]]) -> int:
    score = 0
    for keyword, weight in keywords:
        if contains_keyword(text, keyword):
            score += weight
    return score


def score_document_type(doc_type: int, text: str) -> int:
    if doc_type not in _TYPE_KEYWORDS:
        return 0

    normalized = _normalize(text)
    score = _keyword_score(text, _TYPE_KEYWORDS[doc_type])

    if doc_type == 1 and _CREDIT_CODE_PATTERN.search(normalized):
        score += 3
    if doc_type in _ID_PATTERN_TYPES and _ID_CARD_PATTERN.search(normalized):
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

    if doc_type == 6:
        from ocr_rel.parsers.type6_grade_protection import is_type6_content

        if is_type6_content(text):
            return

    if doc_type == 7:
        from ocr_rel.parsers.type7_credit_report import is_credit_report_content

        if is_credit_report_content(text):
            return

    if doc_type == 8:
        from ocr_rel.parsers.type8_credit_proof import is_credit_proof_content

        if is_credit_proof_content(text):
            return

    if doc_type in {9, 10, 11}:
        from ocr_rel.parsers.type8_credit_proof import is_credit_proof_content

        if is_credit_proof_content(text):
            return

    if detected_type is not None and detected_type != doc_type:
        if doc_type in _ID_CARD_TYPES and detected_type in _ID_CARD_TYPES and declared_score >= 3:
            return
        detected_name = ATTACHMENT_TYPE_NAMES.get(detected_type, f"type-{detected_type}")
        raise DocumentTypeMismatchError(
            f"文件内容与声明类型不一致：声明为「{declared_name}」，"
            f"识别内容更符合「{detected_name}」"
        )

    if declared_score < 3:
        raise DocumentTypeMismatchError(
            f"文件内容与声明类型不一致：无法从识别内容确认该文件为「{declared_name}」"
        )
