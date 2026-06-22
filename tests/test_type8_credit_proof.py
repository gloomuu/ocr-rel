import pytest

from ocr_rel.llm.validator import normalize_detail
from ocr_rel.parsers.type8_credit_proof import (
    STANDARD_NO_DISHONESTY_RESULT,
    CreditProofParser,
    finalize_credit_proof_detail,
    is_credit_proof_content,
    ocr_indicates_dishonesty,
    ocr_indicates_no_dishonesty,
)
from ocr_rel.services.extraction_service import ExtractionService


CREDIT_PROOF_COMPANY_TEXT = """
中国执行信息公开网
全国法院失信被执行人名单信息公布与查询
被执行人姓名/名称：河南测试售电有限公司
证件号码/组织机构代码：91410000MA9ABCDEF0
查询结果：在全国范围内没有找到符合条件的信息
"""


CREDIT_PROOF_PERSON_TEXT = """
中国执行信息公开网
失信被执行人查询
被执行人姓名：张三
证件号码：410105199001011234
查询结果：在全国范围内没有找到
"""


CREDIT_PROOF_WITH_RECORDS_TEXT = """
中国执行信息公开网
失信被执行人查询
被执行人姓名：李四
查询结果：共查询到2条
"""


def test_is_credit_proof_content() -> None:
    assert is_credit_proof_content(CREDIT_PROOF_COMPANY_TEXT)
    assert not is_credit_proof_content("这是一段无关文字")


def test_ocr_indicates_no_dishonesty() -> None:
    assert ocr_indicates_no_dishonesty(CREDIT_PROOF_COMPANY_TEXT)
    assert ocr_indicates_no_dishonesty(CREDIT_PROOF_PERSON_TEXT)
    assert not ocr_indicates_no_dishonesty(CREDIT_PROOF_WITH_RECORDS_TEXT)


def test_ocr_indicates_dishonesty() -> None:
    assert ocr_indicates_dishonesty(CREDIT_PROOF_WITH_RECORDS_TEXT)
    assert not ocr_indicates_dishonesty(CREDIT_PROOF_PERSON_TEXT)


def test_credit_proof_parser_company() -> None:
    result = CreditProofParser().parse(CREDIT_PROOF_COMPANY_TEXT)
    assert result["executedPersonName"] == "河南测试售电有限公司"
    assert result["queryResult"] == STANDARD_NO_DISHONESTY_RESULT


def test_credit_proof_parser_person() -> None:
    result = CreditProofParser().parse(CREDIT_PROOF_PERSON_TEXT)
    assert result["executedPersonName"] == "张三"
    assert result["queryResult"] == STANDARD_NO_DISHONESTY_RESULT


def test_credit_proof_parser_keeps_positive_query_result() -> None:
    result = CreditProofParser().parse(CREDIT_PROOF_WITH_RECORDS_TEXT)
    assert result["executedPersonName"] == "李四"
    assert result["queryResult"] == "共查询到2条"


def test_finalize_credit_proof_detail_overrides_llm_output_when_ocr_is_clean() -> None:
    detail = finalize_credit_proof_detail(
        {
            "executedPersonName": "张三",
            "queryResult": "在全国范围内没有找到",
        },
        CREDIT_PROOF_PERSON_TEXT,
    )
    assert detail["queryResult"] == STANDARD_NO_DISHONESTY_RESULT


def test_normalize_detail_type8() -> None:
    detail = normalize_detail(
        8,
        {
            "executedPersonName": "张三",
            "queryResult": STANDARD_NO_DISHONESTY_RESULT,
        },
    )
    assert detail["executedPersonName"] == "张三"
    assert detail["queryResult"] == STANDARD_NO_DISHONESTY_RESULT


@pytest.mark.asyncio
async def test_extraction_service_finalizes_credit_proof_from_ocr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("ocr_rel.services.extraction_service.settings.extraction_strategy", "llm")

    class FakeLlmExtractor:
        is_available = True

        async def extract(self, doc_type, ocr_text, *, personnel=None, attachment_name=None):
            return {
                "executedPersonName": "张三",
                "queryResult": "在全国范围内没有找到",
            }

    service = ExtractionService(llm_extractor=FakeLlmExtractor())
    detail = await service.extract(8, CREDIT_PROOF_PERSON_TEXT)
    assert detail["queryResult"] == STANDARD_NO_DISHONESTY_RESULT
