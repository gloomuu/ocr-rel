import json

import pytest

from ocr_rel.config import settings
from ocr_rel.llm.client import _parse_json_content
from ocr_rel.llm.validator import is_detail_sufficient, normalize_detail
from ocr_rel.services.extraction_service import ExtractionService


def test_parse_json_content_plain() -> None:
    payload = _parse_json_content('{"companyName":"测试公司"}')
    assert payload["companyName"] == "测试公司"


def test_parse_json_content_markdown_fence() -> None:
    payload = _parse_json_content(
        """```json
{"companyName":"测试公司","unifiedSocialCreditCode":"91410000MA9ABCDEF0"}
```"""
    )
    assert payload["unifiedSocialCreditCode"] == "91410000MA9ABCDEF0"


def test_normalize_detail_type1() -> None:
    detail = normalize_detail(
        1,
        {
            "unifiedSocialCreditCode": "91410000MA9ABCDEF0",
            "companyName": "测试公司",
            "establishDate": "2008年11月04日",
            "registeredAddress": "深圳市南山区",
            "registerAuthority": "深圳市市场监督管理局",
            "approvalDate": "2020-05-20",
        },
    )
    assert detail["establishDate"] == "2008-11-04"
    assert detail["approvalDate"] == "2020-05-20"


def test_normalize_detail_rejects_invalid_credit_code() -> None:
    detail = normalize_detail(1, {"unifiedSocialCreditCode": "invalid"})
    assert detail["unifiedSocialCreditCode"] == ""


def test_is_detail_sufficient() -> None:
    assert is_detail_sufficient(1, {"companyName": "测试"})
    assert not is_detail_sufficient(1, {"companyName": ""})


@pytest.mark.asyncio
async def test_llm_extractor_extract_cover_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "llm_api_key", "test-key")
    cover_text = (
        "深圳壹创国际设计股份有限公司\n"
        "致同会计师事务所 (特殊普通合伙)\n"
        "此码用于证明该审计报告是否由具有执业许可的会计师事务所出具\n"
        "报告编码：京25CLW5B6TX"
    )

    class FakeClient:
        is_configured = True

        async def chat_json(self, *, system_prompt: str, user_prompt: str, images=None) -> dict:
            assert "accountingFirmName" in system_prompt
            assert "此码用于证明" in user_prompt
            assert images is None
            return {
                "companyName": "深圳壹创国际设计股份有限公司",
                "accountingFirmName": "致同会计师事务所(特殊普通合伙)",
                "reportCode": "京25CLW5B6TX",
            }

    from ocr_rel.llm.extractor import LlmExtractor

    extractor = LlmExtractor(client=FakeClient())
    result = await extractor.extract_cover_fields(cover_text)
    assert result["accountingFirmName"] == "致同会计师事务所(特殊普通合伙)"


@pytest.mark.asyncio
async def test_llm_extractor_extract_total_assets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "llm_api_key", "test-key")

    class FakeClient:
        is_configured = True

        async def chat_json(self, *, system_prompt: str, user_prompt: str, images=None) -> dict:
            assert "totalAssets" in system_prompt
            assert "资产总计" in user_prompt
            assert images is None
            return {"totalAssets": "188,364,096.84"}

    from ocr_rel.llm.extractor import LlmExtractor

    extractor = LlmExtractor(client=FakeClient())
    result = await extractor.extract_total_assets("资产总计 188，364，096.84")
    assert result == "188364096.84"


@pytest.mark.asyncio
async def test_extraction_service_uses_llm_when_available(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "extraction_strategy", "llm")
    monkeypatch.setattr(settings, "llm_api_key", "test-key")
    class FakeLlmExtractor:
        is_available = True

        async def extract(self, doc_type, ocr_text, *, personnel=None, attachment_name=None):
            return {
                "unifiedSocialCreditCode": "91410000MA9ABCDEF0",
                "companyName": "LLM公司",
                "establishDate": "2008-11-04",
                "registeredAddress": "深圳市",
                "registerAuthority": "深圳市市场监督管理局",
                "approvalDate": "2020-05-20",
            }

    service = ExtractionService(llm_extractor=FakeLlmExtractor())
    detail = await service.extract(1, "ocr text")
    assert detail["companyName"] == "LLM公司"


@pytest.mark.asyncio
async def test_extraction_service_fallback_to_regex() -> None:
    class FailingLlmExtractor:
        is_available = True

        async def extract(self, doc_type, ocr_text, *, personnel=None, attachment_name=None):
            raise RuntimeError("llm down")

    text = """
    名称：正则公司
    统一社会信用代码：91410000MA9ABCDEF0
    住所：河南省郑州市金水区
    成立日期：2020年05月18日
    登记机关：郑州市市场监督管理局
    核准日期：2023年01月10日
    """
    service = ExtractionService(llm_extractor=FailingLlmExtractor())
    detail = await service.extract(1, text)
    assert detail["companyName"] == "正则公司"
