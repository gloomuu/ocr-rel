from __future__ import annotations

from typing import Any

from ocr_rel.parsers.base import BaseParser
from ocr_rel.parsers.type2_legal_person_id import LegalPersonIdParser


class EmployeeIdParser(BaseParser):
    doc_type = 5

    def __init__(self) -> None:
        self._id_parser = LegalPersonIdParser()

    def parse(
        self,
        text: str,
        personnel: str | None = None,
        attachment_name: str | None = None,
    ) -> dict[str, Any]:
        return self._id_parser.parse(text, personnel=personnel)
