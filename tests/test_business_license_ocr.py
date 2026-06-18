import pytest
from PIL import Image

from ocr_rel.config import settings
from ocr_rel.ocr.service import BusinessLicenseOcrResult
from ocr_rel.services.business_license_ocr import (
    _merge_approval_date,
    _merge_register_authority,
    recognize_business_license_detail,
)
from tests.test_text_utils import YICHUANG_OCR_TEXT


@pytest.mark.asyncio
async def test_recognize_business_license_detail_uses_llm_for_register_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "llm_api_key", "test-key")
    monkeypatch.setattr(settings, "llm_model", "qwen-vl-plus")

    class FakeEngine:
        async def recognize_image(self, image):
            width, _ = image.size
            if width <= 500:
                return "深圳市市场监督管理局"
            return YICHUANG_OCR_TEXT

    class FakeLlmExtractor:
        is_available = True

        async def extract_seal_fields(self, page_text: str, seal_text: str = "", **kwargs) -> dict[str, str]:
            assert YICHUANG_OCR_TEXT in page_text
            assert seal_text == "深圳市市场监督管理局"
            assert kwargs.get("seal_images")
            return {
                "registerAuthority": "深圳市市场监督管理局",
                "approvalDate": "2020-05-20",
            }

    image = Image.new("RGB", (1000, 1400), color=(255, 255, 255))
    detail, text = await recognize_business_license_detail(
        FakeEngine(),
        [image],
        llm_extractor=FakeLlmExtractor(),
    )
    assert "91440300682024797J" in text
    assert detail["companyName"] == "深圳壹创国际设计股份有限公司"
    assert detail["registerAuthority"] == "深圳市市场监督管理局"
    assert detail["approvalDate"] == "2020-05-20"


@pytest.mark.asyncio
async def test_recognize_business_license_detail_falls_back_to_regex_when_llm_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "llm_model", "qwen-vl-plus")

    class FakeEngine:
        async def recognize_image(self, image):
            return (
                "统一社会信用代码 91410000MA9ABCDEF0\n"
                "名称 正则公司\n"
                "登记机关 郑州市市场监督管理局\n"
                "核准日期 2023年01月10日"
            )

    class FailingLlmExtractor:
        is_available = True

        async def extract_seal_fields(self, page_text: str, seal_text: str = "", **kwargs) -> dict[str, str]:
            raise RuntimeError("llm down")

    image = Image.new("RGB", (1000, 1400), color=(255, 255, 255))
    detail, _ = await recognize_business_license_detail(
        FakeEngine(),
        [image],
        llm_extractor=FailingLlmExtractor(),
    )
    assert detail["registerAuthority"] == "郑州市市场监督管理局"


@pytest.mark.asyncio
async def test_llm_extractor_extract_seal_fields_requires_vision_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "llm_api_key", "test-key")
    monkeypatch.setattr(settings, "llm_model", "qwen-plus")

    from ocr_rel.llm.extractor import LlmExtractor

    extractor = LlmExtractor(client=type("C", (), {"is_configured": True})())
    with pytest.raises(ValueError, match="does not support vision"):
        await extractor.extract_seal_fields(
            YICHUANG_OCR_TEXT,
            seal_images=[Image.new("RGB", (1, 1))],
        )


@pytest.mark.asyncio
async def test_llm_extractor_extract_seal_fields_with_vision(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "llm_api_key", "test-key")
    monkeypatch.setattr(settings, "llm_model", "qwen-vl-plus")
    seal_image = Image.new("RGB", (100, 100), color=(255, 0, 0))

    class FakeClient:
        is_configured = True

        async def chat_json(
            self,
            *,
            system_prompt: str,
            user_prompt: str,
            images: list[Image.Image] | None = None,
        ) -> dict:
            assert "禁止根据住所" in system_prompt
            assert "附件为营业执照右下角公章区域图片" in user_prompt
            assert images is not None and len(images) == 1
            return {
                "registerAuthority": "深圳市市场监督管理局",
                "approvalDate": "2020-05-20",
            }

    from ocr_rel.llm.extractor import LlmExtractor

    extractor = LlmExtractor(client=FakeClient())
    result = await extractor.extract_seal_fields(
        YICHUANG_OCR_TEXT,
        "",
        seal_images=[seal_image],
    )
    assert result["registerAuthority"] == "深圳市市场监督管理局"
    assert result["approvalDate"] == "2020-05-20"


@pytest.mark.asyncio
async def test_recognize_business_license_skips_llm_for_non_vision_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "llm_api_key", "test-key")
    monkeypatch.setattr(settings, "llm_model", "qwen-plus")

    class FakeEngine:
        async def recognize_image(self, image):
            width, _ = image.size
            if width <= 500:
                return ""
            return YICHUANG_OCR_TEXT

    class FakeLlmExtractor:
        is_available = True

        async def extract_seal_fields(self, *args, **kwargs) -> dict[str, str]:
            raise AssertionError("non-vision model should not call LLM for seal fields")

    image = Image.new("RGB", (1000, 1400), color=(255, 255, 255))
    detail, _ = await recognize_business_license_detail(
        FakeEngine(),
        [image],
        llm_extractor=FakeLlmExtractor(),
    )
    assert detail["registerAuthority"] == ""
    assert detail["approvalDate"] == ""


def test_business_license_ocr_result_combined_text() -> None:
    result = BusinessLicenseOcrResult(page_text="全文", seal_text="公章")
    assert result.combined_text == "全文\n公章"

    empty_seal = BusinessLicenseOcrResult(page_text="全文", seal_text="")
    assert empty_seal.combined_text == "全文"


def test_merge_register_authority_prefers_ocr() -> None:
    assert _merge_register_authority("郑州市市场监督管理局", "深圳市市场监督管理局") == (
        "郑州市市场监督管理局"
    )


def test_merge_register_authority_uses_llm_when_ocr_empty() -> None:
    assert _merge_register_authority("", "深圳市市场监督管理局") == "深圳市市场监督管理局"


def test_merge_approval_date_prefers_ocr() -> None:
    assert _merge_approval_date("2023-01-10", "2020-05-20", establish_date="2008-11-04") == (
        "2023-01-10"
    )


@pytest.mark.asyncio
async def test_recognize_business_license_detail_ocr_wins_over_conflicting_llm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "llm_model", "qwen-vl-plus")

    class FakeEngine:
        async def recognize_image(self, image):
            return (
                "统一社会信用代码 91410000MA9ABCDEF0\n"
                "名称 正则公司\n"
                "登记机关 郑州市市场监督管理局\n"
                "核准日期 2023年01月10日"
            )

    class FakeLlmExtractor:
        is_available = True

        async def extract_seal_fields(self, page_text: str, seal_text: str = "", **kwargs) -> dict[str, str]:
            return {
                "registerAuthority": "深圳市市场监督管理局",
                "approvalDate": "2020-05-20",
            }

    image = Image.new("RGB", (1000, 1400), color=(255, 255, 255))
    detail, _ = await recognize_business_license_detail(
        FakeEngine(),
        [image],
        llm_extractor=FakeLlmExtractor(),
    )
    assert detail["registerAuthority"] == "郑州市市场监督管理局"
    assert detail["approvalDate"] == "2023-01-10"
