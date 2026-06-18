from ocr_rel.llm.validator import normalize_detail
from ocr_rel.parsers.type4_capital_verification import (
    CapitalVerificationParser,
    extract_cover_fields,
    extract_capital_verification_report_code,
)


COVER_TEXT = """
验资报告
被验资单位：河南测试售电有限公司
会计师事务所：立信会计师事务所（特殊普通合伙）河南分所
验资报告文号：京信验字(2023)第12345号
注册资本：人民币2000万元
"""


def test_extract_cover_fields() -> None:
    detail = extract_cover_fields(COVER_TEXT)
    assert detail["companyName"] == "河南测试售电有限公司"
    assert "立信会计师事务所" in detail["accountingFirmName"]
    assert detail["reportCode"] == "京信验字(2023)第12345号"


def test_extract_report_code_from_encoding_label() -> None:
    text = "报告编码：京25CLW5B6TX"
    assert extract_capital_verification_report_code(text) == "京25CLW5B6TX"


def test_capital_verification_parser() -> None:
    result = CapitalVerificationParser().parse(COVER_TEXT)
    assert result["companyName"] == "河南测试售电有限公司"
    assert "立信会计师事务所" in result["accountingFirmName"]
    assert result["reportCode"] == "京信验字(2023)第12345号"


def test_normalize_detail_type4() -> None:
    detail = normalize_detail(
        4,
        {
            "companyName": "河南测试售电有限公司",
            "accountingFirmName": "立信会计师事务所",
            "reportCode": "京信验字(2023)第12345号",
        },
    )
    assert detail["companyName"] == "河南测试售电有限公司"
    assert detail["reportCode"] == "京信验字(2023)第12345号"
