from __future__ import annotations

import re
from typing import Any

from ocr_rel.parsers.base import BaseParser


class LegalPersonIdParser(BaseParser):
    doc_type = 2

    def parse(self, text: str, personnel: str | None = None) -> dict[str, Any]:
        compact = self._normalize(text)
        name = self._extract_name(text, compact)
        id_card = self._extract_id_card(compact)

        return {
            "name": name or "",
            "idCardNumber": id_card or "",
        }

    def _extract_name(self, text: str, compact: str) -> str | None:
        match = re.search(r"姓名[:：]?\s*([\u4e00-\u9fff·]{2,10})", text)
        if match:
            return match.group(1).strip()
        match = re.search(r"姓名([\u4e00-\u9fff·]{2,10})", compact)
        if match:
            return match.group(1).strip()
        return None

    def _extract_id_card(self, compact: str) -> str | None:
        match = re.search(r"(\d{17}[\dXx])", compact)
        if match:
            return match.group(1).upper()
        return None
