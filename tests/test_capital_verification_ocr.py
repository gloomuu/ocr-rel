import pytest
from PIL import Image

from ocr_rel.parsers.type4_capital_verification import extract_cover_fields
from ocr_rel.services.capital_verification_ocr import recognize_capital_verification_detail


COVER_TEXT = """
验资报告
被验资单位：河南测试售电有限公司
会计师事务所：立信会计师事务所（特殊普通合伙）河南分所
验资报告文号：京信验字(2023)第12345号
"""


class FakeCapitalOcrEngine:
    def __init__(self, pages: list[str]) -> None:
        self._pages = pages
        self._index = 0

    async def recognize_image(self, image: Image.Image) -> str:
        if self._index >= len(self._pages):
            return ""
        text = self._pages[self._index]
        self._index += 1
        return text


class FakeCapitalLlmExtractor:
    is_available = True

    def __init__(self, *, cover_fields: dict[str, str] | None = None) -> None:
        self._cover_fields = cover_fields or {
            "companyName": "河南测试售电有限公司",
            "accountingFirmName": "立信会计师事务所（特殊普通合伙）河南分所",
            "reportCode": "京信验字(2023)第12345号",
        }
        self.cover_calls: list[str] = []

    async def extract_capital_verification_cover_fields(self, cover_text: str) -> dict[str, str]:
        self.cover_calls.append(cover_text)
        return dict(self._cover_fields)


def test_extract_cover_fields_regex() -> None:
    detail = extract_cover_fields(COVER_TEXT)
    assert detail["companyName"] == "河南测试售电有限公司"
    assert "立信会计师事务所" in detail["accountingFirmName"]
    assert detail["reportCode"] == "京信验字(2023)第12345号"


@pytest.mark.asyncio
async def test_recognize_capital_verification_uses_llm_on_cover_page() -> None:
    engine = FakeCapitalOcrEngine([COVER_TEXT])
    llm = FakeCapitalLlmExtractor()

    detail, cover_text = await recognize_capital_verification_detail(
        engine, [Image.new("RGB", (1, 1))], llm_extractor=llm
    )

    assert cover_text == COVER_TEXT.strip()
    assert llm.cover_calls == [COVER_TEXT.strip()]
    assert detail["companyName"] == "河南测试售电有限公司"
    assert detail["reportCode"] == "京信验字(2023)第12345号"


@pytest.mark.asyncio
async def test_recognize_capital_verification_falls_back_to_regex() -> None:
    engine = FakeCapitalOcrEngine([COVER_TEXT])

    class UnavailableLlm:
        is_available = False

    detail, _ = await recognize_capital_verification_detail(
        engine, [Image.new("RGB", (1, 1))], llm_extractor=UnavailableLlm()
    )

    assert detail["companyName"] == "河南测试售电有限公司"
    assert detail["reportCode"] == "京信验字(2023)第12345号"
