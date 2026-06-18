from ocr_rel.llm.validator import normalize_detail
from ocr_rel.parsers.type5_employee_id import EmployeeIdParser


ID_CARD_TEXT = """
中华人民共和国
居民身份证
姓名李四
性别男民族汉
出生1992年05月20日
住址河南省郑州市金水区
公民身份号码410105199205201234
"""


def test_employee_id_parser() -> None:
    result = EmployeeIdParser().parse(ID_CARD_TEXT)
    assert result["name"] == "李四"
    assert result["idCardNumber"] == "410105199205201234"


def test_normalize_detail_type5() -> None:
    detail = normalize_detail(
        5,
        {
            "name": "李四",
            "idCardNumber": "410105199205201234",
        },
    )
    assert detail["name"] == "李四"
    assert detail["idCardNumber"] == "410105199205201234"
