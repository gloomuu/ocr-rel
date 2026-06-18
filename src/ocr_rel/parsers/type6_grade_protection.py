from __future__ import annotations

import re
from typing import Any, Literal

from ocr_rel.parsers.base import BaseParser
from ocr_rel.parsers.text_utils import (
    contains_keyword,
    extract_company_name,
    extract_labeled_field,
)
from ocr_rel.parsers.type6_software_copyright import (
    extract_copyright_owner,
    extract_software_copyright_detail,
)

Type6DocumentKind = Literal["software_copyright", "grade_protection", "unknown"]

# 首页 OCR 主特征词（优先于其它关键词）
GRADE_PROTECTION_PRIMARY_MARKERS = (
    "信息系统安全等级",
    "网络安全等级保护",
    "信息安全等级保护",
    "等级保护备案证明",
)
SOFTWARE_COPYRIGHT_PRIMARY_MARKERS = (
    "软件著作权",
    "计算机软件著作权",
    "著作权登记证书",
)

SYSTEM_LEVEL_LABELS = [
    "安全保护等级",
    "等级保护级别",
    "保护等级",
    "系统等保级别",
    "系统等级",
    "定级等级",
]

COPYRIGHT_OWNER_LABELS = [
    "著作权人",
    "权利人",
]

GRADE_PROTECTION_COMPANY_LABELS = [
    "单位名称",
    "备案单位",
    "单位",
    "公司名称",
    "企业名称",
]

GRADE_PROTECTION_SECONDARY_MARKERS = (
    "等级保护",
    "等保",
    "备案证明",
    "安全保护等级",
    "备案公安机关",
    "备案号",
)

SOFTWARE_COPYRIGHT_SECONDARY_MARKERS = (
    "著作权登记",
    "计算机软件著作权",
    "著作权人",
    "登记号",
)

_LEVEL_CN = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5}
_LEVEL_NAMES = {1: "一级", 2: "二级", 3: "三级", 4: "四级", 5: "五级"}

SYSTEM_LEVEL_PATTERN = re.compile(r"第?\s*([一二三四五1-5])\s*级")


def normalize_system_level(value: str) -> str:
    if not value:
        return ""

    compact = re.sub(r"\s+", "", value.strip())
    match = SYSTEM_LEVEL_PATTERN.search(compact)
    if not match:
        return ""

    token = match.group(1)
    if token.isdigit():
        level = int(token)
    else:
        level = _LEVEL_CN.get(token, 0)

    if 1 <= level <= 5:
        return _LEVEL_NAMES[level]
    return ""


def extract_system_level(text: str) -> str | None:
    labeled = extract_labeled_field(text, SYSTEM_LEVEL_LABELS)
    if labeled:
        normalized = normalize_system_level(labeled)
        if normalized:
            return normalized

    labeled_patterns = [
        r"安全保护等级[:：]?\s*(第?\s*[一二三四五1-5]\s*级)",
        r"等级保护级别[:：]?\s*(第?\s*[一二三四五1-5]\s*级)",
        r"保护等级[:：]?\s*(第?\s*[一二三四五1-5]\s*级)",
    ]
    for pattern in labeled_patterns:
        match = re.search(pattern, text)
        if match:
            normalized = normalize_system_level(match.group(1))
            if normalized:
                return normalized

    for match in SYSTEM_LEVEL_PATTERN.finditer(text):
        normalized = normalize_system_level(match.group(0))
        if normalized:
            return normalized
    return None


def _trim_company_noise(value: str) -> str:
    trimmed = value.strip(" ：:;；,.，。")
    for marker in ("系统名称", "备案号", "备案公安机关", "安全保护等级", "软件名称", "登记号"):
        index = trimmed.find(marker)
        if index > 0:
            trimmed = trimmed[:index]
    return trimmed.strip(" ：:;；,.，。")


def extract_grade_protection_company_name(text: str) -> str | None:
    labeled = extract_labeled_field(text, GRADE_PROTECTION_COMPANY_LABELS)
    if labeled:
        cleaned = _trim_company_noise(labeled)
        if cleaned and len(cleaned) >= 4:
            return cleaned

    match = re.search(
        r"单位名称[:：]?\s*([\u4e00-\u9fff（）()·]{4,80}"
        r"(?:有限责任公司|股份有限公司|有限公司|集团有限公司|公司|企业))",
        text,
    )
    if match:
        return _trim_company_noise(match.group(1))

    company = extract_company_name(text)
    if company:
        return _trim_company_noise(company)
    return None


def extract_grade_protection_detail(text: str) -> dict[str, str]:
    return {
        "copyrightOwner": "",
        "companyName": extract_grade_protection_company_name(text) or "",
        "systemLevel": extract_system_level(text) or "",
    }


def detect_type6_document_kind(text: str) -> Type6DocumentKind:
    """Classify type-6 PDF by OCR keywords (typically from the first page)."""
    if any(contains_keyword(text, marker) for marker in GRADE_PROTECTION_PRIMARY_MARKERS):
        return "grade_protection"
    if any(contains_keyword(text, marker) for marker in SOFTWARE_COPYRIGHT_PRIMARY_MARKERS):
        return "software_copyright"

    grade_score = sum(
        1 for marker in GRADE_PROTECTION_SECONDARY_MARKERS if contains_keyword(text, marker)
    )
    soft_score = sum(
        1 for marker in SOFTWARE_COPYRIGHT_SECONDARY_MARKERS if contains_keyword(text, marker)
    )

    if grade_score > soft_score and grade_score >= 1:
        return "grade_protection"
    if soft_score > grade_score and soft_score >= 1:
        return "software_copyright"
    if grade_score >= 1:
        return "grade_protection"
    if soft_score >= 1:
        return "software_copyright"
    return "unknown"


def is_type6_content(text: str) -> bool:
    """True when OCR text looks like grade-protection or software-copyright material."""
    if detect_type6_document_kind(text) != "unknown":
        return True

    if extract_system_level(text):
        return True

    if extract_labeled_field(text, COPYRIGHT_OWNER_LABELS):
        return True

    if extract_labeled_field(text, GRADE_PROTECTION_COMPANY_LABELS) and (
        contains_keyword(text, "等级保护")
        or contains_keyword(text, "等保")
        or contains_keyword(text, "备案")
    ):
        return True

    if contains_keyword(text, "登记号") and (
        contains_keyword(text, "著作权")
        or contains_keyword(text, "版权局")
    ):
        return True

    return False


def resolve_type6_document_kind(
    text: str,
    attachment_name: str | None = None,
) -> Type6DocumentKind:
    """Backward-compatible alias; attachment_name is ignored."""
    del attachment_name
    return detect_type6_document_kind(text)


def extract_type6_detail(
    text: str,
    *,
    attachment_name: str | None = None,
) -> dict[str, str]:
    del attachment_name
    kind = detect_type6_document_kind(text)

    if kind == "software_copyright":
        return extract_software_copyright_detail(text)

    if kind == "grade_protection":
        return extract_grade_protection_detail(text)

    detail = extract_software_copyright_detail(text)
    grade_detail = extract_grade_protection_detail(text)
    detail["companyName"] = grade_detail["companyName"]
    detail["systemLevel"] = grade_detail["systemLevel"]
    return detail


class TechSupportDocParser(BaseParser):
    doc_type = 6

    def parse(
        self,
        text: str,
        personnel: str | None = None,
        attachment_name: str | None = None,
    ) -> dict[str, Any]:
        return extract_type6_detail(text, attachment_name=attachment_name)


GradeProtectionParser = TechSupportDocParser
