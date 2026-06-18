from __future__ import annotations

import re
from typing import Any

from ocr_rel.parsers.base import BaseParser
from ocr_rel.parsers.text_utils import extract_company_name, extract_labeled_field

COPYRIGHT_OWNER_LABELS = [
    "著作权人",
    "权利人",
]


def _trim_company_noise(value: str) -> str:
    trimmed = value.strip(" ：:;；,.，。")
    for marker in ("系统名称", "备案号", "备案公安机关", "安全保护等级", "软件名称", "登记号"):
        index = trimmed.find(marker)
        if index > 0:
            trimmed = trimmed[:index]
    return trimmed.strip(" ：:;；,.，。")


def extract_copyright_owner(text: str) -> str | None:
    labeled = extract_labeled_field(text, COPYRIGHT_OWNER_LABELS)
    if labeled:
        cleaned = _trim_company_noise(labeled)
        if cleaned and len(cleaned) >= 4:
            return cleaned

    match = re.search(
        r"著作权人[:：]?\s*([\u4e00-\u9fff（）()·]{4,80}"
        r"(?:有限责任公司|股份有限公司|有限公司|集团有限公司|公司|企业))",
        text,
    )
    if match:
        return _trim_company_noise(match.group(1))

    company = extract_company_name(text)
    if company:
        return _trim_company_noise(company)
    return None


def extract_software_copyright_detail(text: str) -> dict[str, str]:
    return {
        "copyrightOwner": extract_copyright_owner(text) or "",
        "companyName": "",
        "systemLevel": "",
    }


class SoftwareCopyrightParser(BaseParser):
    doc_type = 6

    def parse(
        self,
        text: str,
        personnel: str | None = None,
        attachment_name: str | None = None,
    ) -> dict[str, Any]:
        del personnel, attachment_name
        return extract_software_copyright_detail(text)
