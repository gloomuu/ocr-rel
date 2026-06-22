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


CAPITAL_VERIFICATION_TEXT = (
    "验资报告\n"
    "被验资单位：河南测试售电有限公司\n"
    "会计师事务所：立信会计师事务所（特殊普通合伙）\n"
    "验资报告文号：京信验字(2023)第12345号\n"
    "注册资本：人民币2000万元\n"
    "实收资本：人民币2000万元"
)


def test_validate_capital_verification_passes() -> None:
    validate_document_type(4, CAPITAL_VERIFICATION_TEXT)
    assert detect_document_type(CAPITAL_VERIFICATION_TEXT) == 4


def test_validate_capital_verification_with_audit_report_text_fails() -> None:
    with pytest.raises(DocumentTypeMismatchError, match="审计报告"):
        validate_document_type(4, AUDIT_REPORT_TEXT)


def test_validate_audit_report_with_capital_verification_text_fails() -> None:
    with pytest.raises(DocumentTypeMismatchError, match="验资报告"):
        validate_document_type(3, CAPITAL_VERIFICATION_TEXT)


def test_validate_employee_id_passes() -> None:
    validate_document_type(5, ID_CARD_TEXT)
    assert detect_document_type(ID_CARD_TEXT) in {2, 5}


def test_validate_employee_id_with_business_license_text_fails() -> None:
    with pytest.raises(DocumentTypeMismatchError, match="营业执照"):
        validate_document_type(5, BUSINESS_LICENSE_TEXT)


def test_validate_legal_person_id_with_same_id_card_text_as_type5_passes() -> None:
    validate_document_type(5, ID_CARD_TEXT)


GRADE_PROTECTION_TEXT = (
    "信息系统安全等级保护备案证明\n"
    "单位名称：河南测试售电有限公司\n"
    "系统名称：售电业务技术支持系统\n"
    "安全保护等级：第三级\n"
    "备案公安机关：郑州市公安局"
)


def test_validate_grade_protection_passes() -> None:
    validate_document_type(6, GRADE_PROTECTION_TEXT)
    assert detect_document_type(GRADE_PROTECTION_TEXT) == 6


def test_validate_grade_protection_with_business_license_text_fails() -> None:
    with pytest.raises(DocumentTypeMismatchError, match="营业执照"):
        validate_document_type(6, BUSINESS_LICENSE_TEXT)


SOFTWARE_COPYRIGHT_TEXT = (
    "计算机软件著作权登记证书\n"
    "软件名称：售电业务技术支持系统V1.0\n"
    "著作权人：河南测试售电有限公司\n"
    "登记号：2024SR1234567"
)


def test_validate_software_copyright_passes() -> None:
    validate_document_type(6, SOFTWARE_COPYRIGHT_TEXT)
    assert detect_document_type(SOFTWARE_COPYRIGHT_TEXT) == 6


def test_validate_type6_passes_with_primary_marker_only() -> None:
    validate_document_type(6, "信息系统安全等级保护备案证明\n单位名称：测试公司")


def test_validate_type6_passes_with_network_security_title() -> None:
    validate_document_type(6, "网络安全等级保护备案证明\n单位名称：测试公司")


def test_validate_type6_passes_with_spaced_ocr_text() -> None:
    validate_document_type(6, "信 息 系 统 安 全 等 级 保 护 备 案 证 明\n单 位 名 称：测试公司")


CREDIT_REPORT_TEXT = (
    "个人信用报告\n"
    "（本人版）\n"
    "报告编号：2024062214301234567890\n"
    "被查询者姓名：王五\n"
    "被查询者证件类型：身份证\n"
    "被查询者证件号码：110101198501011234\n"
    "查询机构：某某银行股份有限公司\n"
    "中国人民银行征信中心\n"
    "信息概要\n"
    "信贷记录"
)


def test_validate_credit_report_passes() -> None:
    validate_document_type(7, CREDIT_REPORT_TEXT)
    assert detect_document_type(CREDIT_REPORT_TEXT) == 7


def test_validate_credit_report_with_id_card_text_fails() -> None:
    with pytest.raises(DocumentTypeMismatchError, match="法人身份证"):
        validate_document_type(7, ID_CARD_TEXT)


def test_validate_id_card_with_credit_report_text_fails() -> None:
    with pytest.raises(DocumentTypeMismatchError, match="法人征信报告"):
        validate_document_type(2, CREDIT_REPORT_TEXT)


CREDIT_PROOF_TEXT = (
    "中国执行信息公开网\n"
    "全国法院失信被执行人名单信息公布与查询\n"
    "被执行人姓名/名称：河南测试售电有限公司\n"
    "证件号码/组织机构代码：91410000MA9ABCDEF0\n"
    "查询结果：在全国范围内没有找到符合条件的信息"
)


def test_validate_credit_proof_passes() -> None:
    validate_document_type(8, CREDIT_PROOF_TEXT)
    assert detect_document_type(CREDIT_PROOF_TEXT) == 8


def test_validate_credit_proof_with_credit_report_text_fails() -> None:
    with pytest.raises(DocumentTypeMismatchError, match="法人征信报告"):
        validate_document_type(8, CREDIT_REPORT_TEXT)


def test_validate_credit_report_with_credit_proof_text_fails() -> None:
    with pytest.raises(DocumentTypeMismatchError, match="信用证明"):
        validate_document_type(7, CREDIT_PROOF_TEXT)
