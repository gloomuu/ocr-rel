import pytest

from ocr_rel.services.document_validator import (
    DocumentTypeMismatchError,
    detect_document_type,
    validate_document_type,
)

BUSINESS_LICENSE_TEXT = (
    "营业执照\n"
    "名称：测试售电有限公司\n"
    "统一社会信用代码：91410000MA9ABCDEF0\n"
    "住所：河南省郑州市金水区某某路100号\n"
    "成立日期：2020年05月18日\n"
    "登记机关：郑州市市场监督管理局\n"
    "核准日期：2023年01月10日"
)

ID_CARD_TEXT = (
    "中华人民共和国\n"
    "居民身份证\n"
    "姓名张三\n"
    "性别男民族汉\n"
    "出生1990年01月01日\n"
    "住址河南省郑州市金水区\n"
    "公民身份号码410105199001011234\n"
    "签发机关郑州市公安局\n"
    "有效期限2020.01.01-2040.01.01"
)

AUDIT_REPORT_TEXT = (
    "审计报告\n"
    "被审计单位：河南测试售电有限公司\n"
    "会计师事务所：立信会计师事务所（特殊普通合伙）\n"
    "报告文号：信会师报字[2023]第ZA12345号\n"
    "资产总额：30,000,000.00元\n"
    "审计意见\n"
    "我们审计了后附的财务报表"
)


def test_validate_business_license_passes() -> None:
    validate_document_type(1, BUSINESS_LICENSE_TEXT)
    assert detect_document_type(BUSINESS_LICENSE_TEXT) == 1


def test_validate_id_card_passes() -> None:
    validate_document_type(2, ID_CARD_TEXT)
    assert detect_document_type(ID_CARD_TEXT) == 2


def test_validate_business_license_with_id_card_text_fails() -> None:
    with pytest.raises(DocumentTypeMismatchError, match="法人身份证"):
        validate_document_type(1, ID_CARD_TEXT)


def test_validate_id_card_with_business_license_text_fails() -> None:
    with pytest.raises(DocumentTypeMismatchError, match="营业执照"):
        validate_document_type(2, BUSINESS_LICENSE_TEXT)


def test_validate_unrecognizable_text_fails() -> None:
    with pytest.raises(DocumentTypeMismatchError, match="无法从识别内容确认"):
        validate_document_type(1, "这是一段无关文字")


def test_validate_audit_report_passes() -> None:
    validate_document_type(3, AUDIT_REPORT_TEXT)
    assert detect_document_type(AUDIT_REPORT_TEXT) == 3


def test_validate_audit_report_with_business_license_text_fails() -> None:
    with pytest.raises(DocumentTypeMismatchError, match="营业执照"):
        validate_document_type(3, BUSINESS_LICENSE_TEXT)


def test_validate_business_license_with_audit_report_text_fails() -> None:
    with pytest.raises(DocumentTypeMismatchError, match="审计报告"):
        validate_document_type(1, AUDIT_REPORT_TEXT)
