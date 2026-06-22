from ocr_rel.llm.validator import normalize_detail
from ocr_rel.parsers.type7_credit_report import CreditReportParser, is_credit_report_content


CREDIT_REPORT_TEXT = """
个人信用报告
（本人版）
报告编号：2024062214301234567890
被查询者姓名：王五
被查询者证件类型：身份证
被查询者证件号码：110101198501011234
查询机构：某某银行股份有限公司
中国人民银行征信中心
信息概要
信贷记录
"""


def test_is_credit_report_content() -> None:
    assert is_credit_report_content(CREDIT_REPORT_TEXT)
    assert not is_credit_report_content("这是一段无关文字")


def test_credit_report_parser() -> None:
    result = CreditReportParser().parse(CREDIT_REPORT_TEXT)
    assert result["name"] == "王五"
    assert result["idCardNumber"] == "110101198501011234"


def test_credit_report_parser_falls_back_to_generic_patterns() -> None:
    text = "个人信用报告\n姓名张三\n公民身份号码410105199001011234\n中国人民银行征信中心"
    result = CreditReportParser().parse(text)
    assert result["name"] == "张三"
    assert result["idCardNumber"] == "410105199001011234"


def test_normalize_detail_type7() -> None:
    detail = normalize_detail(
        7,
        {
            "name": "王五",
            "idCardNumber": "110101198501011234",
        },
    )
    assert detail["name"] == "王五"
    assert detail["idCardNumber"] == "110101198501011234"
