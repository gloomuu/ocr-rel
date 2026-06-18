from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Any


class BaseParser(ABC):
    doc_type: int

    @abstractmethod
    def parse(
        self,
        text: str,
        personnel: str | None = None,
        attachment_name: str | None = None,
    ) -> dict[str, Any]:
        pass

    @staticmethod
    def _normalize(text: str) -> str:
        return re.sub(r"\s+", "", text)

    @staticmethod
    def _find_first(patterns: list[str], text: str, *, flags: int = 0) -> str | None:
        for pattern in patterns:
            match = re.search(pattern, text, flags)
            if match:
                return match.group(1).strip()
        return None
