from __future__ import annotations

from typing import Any

from ocr_rel.parsers.base import BaseParser
from ocr_rel.parsers.text_utils import (
    extract_approval_date,
    extract_company_name,
    extract_credit_code,
    extract_date_near_label,
    extract_register_authority,
    extract_registered_address,
)


class BusinessLicenseParser(BaseParser):
    doc_type = 1

    def parse(
        self,
        text: str,
        personnel: str | None = None,
        attachment_name: str | None = None,
    ) -> dict[str, Any]:
        establish_date = extract_date_near_label(text, ["成立日期", "成立时间"]) or ""
        return {
            "unifiedSocialCreditCode": extract_credit_code(text) or "",
            "companyName": extract_company_name(text) or "",
            "establishDate": establish_date,
            "registeredAddress": extract_registered_address(text) or "",
            "registerAuthority": extract_register_authority(text) or "",
            "approvalDate": extract_approval_date(text, establish_date or None) or "",
        }
