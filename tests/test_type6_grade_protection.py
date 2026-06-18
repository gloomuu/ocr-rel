from ocr_rel.llm.validator import normalize_detail
from ocr_rel.parsers.type6_grade_protection import (
    TechSupportDocParser,
    detect_type6_document_kind,
    extract_type6_detail,
    normalize_system_level,
)


GRADE_PROTECTION_TEXT = """
信息系统安全等级保护备案证明
单位名称：河南测试售电有限公司
系统名称：售电业务技术支持系统
安全保护等级：第二级
备案号：41010000000-00001
备案公安机关：郑州市公安局
"""

SOFTWARE_COPYRIGHT_TEXT = """
中华人民共和国国家版权局
计算机软件著作权登记证书
软件名称：售电业务技术支持系统V1.0
著作权人：河南测试售电有限公司
登记号：2024SR1234567
"""


def test_normalize_system_level() -> None:
    assert normalize_system_level("第二级") == "二级"
    assert normalize_system_level("3级") == "三级"


def test_detect_type6_document_kind_from_ocr_keywords() -> None:
    assert detect_type6_document_kind(GRADE_PROTECTION_TEXT) == "grade_protection"
    assert detect_type6_document_kind(SOFTWARE_COPYRIGHT_TEXT) == "software_copyright"
    assert (
        detect_type6_document_kind("网 络 安 全 等 级 保 护 备 案 证 明\n单位名称：测试公司")
        == "grade_protection"
    )


def test_is_type6_content_with_extracted_fields() -> None:
    from ocr_rel.parsers.type6_grade_protection import is_type6_content

    assert is_type6_content("单位名称：河南测试售电有限公司\n安全保护等级：第三级\n备案号：123")
    assert is_type6_content("著作权人：河南测试售电有限公司\n登记号：2024SR1234567")
    assert not is_type6_content(
        "营业执照\n名称：测试售电有限公司\n统一社会信用代码：91410000MA9ABCDEF0"
    )


def test_detect_type6_ignores_attachment_name() -> None:
    assert detect_type6_document_kind(SOFTWARE_COPYRIGHT_TEXT) == "software_copyright"
    assert (
        extract_type6_detail(SOFTWARE_COPYRIGHT_TEXT, attachment_name="等级保护备案证明")[
            "copyrightOwner"
        ]
        == "河南测试售电有限公司"
    )


def test_extract_grade_protection_detail() -> None:
    detail = extract_type6_detail(GRADE_PROTECTION_TEXT)
    assert detail["companyName"] == "河南测试售电有限公司"
    assert detail["systemLevel"] == "二级"
    assert detail["copyrightOwner"] == ""


def test_extract_software_copyright_detail() -> None:
    detail = extract_type6_detail(SOFTWARE_COPYRIGHT_TEXT)
    assert detail["copyrightOwner"] == "河南测试售电有限公司"
    assert detail["companyName"] == ""
    assert detail["systemLevel"] == ""


def test_tech_support_parser() -> None:
    result = TechSupportDocParser().parse(SOFTWARE_COPYRIGHT_TEXT)
    assert result["copyrightOwner"] == "河南测试售电有限公司"


def test_normalize_detail_type6() -> None:
    detail = normalize_detail(
        6,
        {
            "copyrightOwner": "河南测试售电有限公司",
            "companyName": "",
            "systemLevel": "第2级",
        },
    )
    assert detail["copyrightOwner"] == "河南测试售电有限公司"
    assert detail["systemLevel"] == "二级"
