import pytest

from ocr_rel.parsers.text_utils import (
    extract_approval_date,
    extract_approval_date_from_seal,
    extract_company_name,
    extract_credit_code,
    extract_labeled_field,
    extract_register_authority,
    extract_registered_address,
    format_chinese_date,
    is_invalid_register_authority,
)
from ocr_rel.services.extraction_service import ExtractionService


def test_format_chinese_date() -> None:
    assert format_chinese_date("2008年11月04日") == "2008-11-04"


def test_extract_credit_code() -> None:
    assert extract_credit_code("统一社会信用代码 91440300682024797J") == "91440300682024797J"


def test_extract_labeled_field_stops_at_footnote() -> None:
    text = """
    住所
    深圳市罗湖区某路1号
    1.商事主体的经营范围由章程确定。
    """
    assert extract_labeled_field(text, ["住所"], multiline=True) == "深圳市罗湖区某路1号"


def test_extract_register_authority_rejects_footnote_fragment() -> None:
    text = "应向商事登记机关申请\n深圳市市场监督管理局"
    assert extract_register_authority(text) == "深圳市市场监督管理局"


def test_extract_register_authority_labeled() -> None:
    text = "登记机关\n深圳市市场监督管理局\n应向商事登记机关申请"
    assert extract_register_authority(text) == "深圳市市场监督管理局"


def test_extract_register_authority_rejects_footer_supervisor() -> None:
    text = """
    登记机关 2026年03月03日
    国家企业信用信息公示系统网址：http://www.gsxt.gov.cn
    国家市场监督管理总局监制
    """
    assert extract_register_authority(text) is None


def test_extract_register_authority_from_seal_area() -> None:
    text = """
    登记机关
    深圳市市场监督管理局
    2026年03月03日
    国家市场监督管理总局监制
    """
    assert extract_register_authority(text) == "深圳市市场监督管理局"


def test_extract_register_authority_inline_seal() -> None:
    text = "登记机关深圳市市场监督管理局2026年03月03日国家市场监督管理总局监制"
    assert extract_register_authority(text) == "深圳市市场监督管理局"


YICHUANG_OCR_TEXT = (
    "使用! 统一社会信用代码 91440300682024797J 供壹创 营 业执 照 (副 本) "
    "名 深圳壹创国际设计股份有限公司 类 型 非上市股份有限公司 成立日期 2008年11月04日 "
    "法定代表人 吴彦 住 所 深圳市罗湖区笋岗街道田心社区红岭北路2188号广田大厦27层 "
    "o 登记机关 2026年 03月 ( 03日 国家企业信用信息公示系统网址：http：//www.gsxt.gov.cn "
    "国家市场监督管理总局监制"
)


def test_extract_register_authority_rejects_label_only_ocr() -> None:
    assert extract_register_authority(YICHUANG_OCR_TEXT) is None


def test_extract_register_authority_from_appended_seal_ocr() -> None:
    text = YICHUANG_OCR_TEXT + "\n深圳市市场监督管理局"
    assert extract_register_authority(text) == "深圳市市场监督管理局"


def test_is_invalid_register_authority() -> None:
    assert is_invalid_register_authority("登记机关") is True
    assert is_invalid_register_authority("国家市场监督管理总局") is True
    assert is_invalid_register_authority("深圳市市场监督管理局") is False


@pytest.mark.asyncio
async def test_finalize_clears_label_only_register_authority() -> None:
    detail = ExtractionService._finalize_business_license_detail(
        {"registerAuthority": "登记机关", "approvalDate": "2026-03-03"},
        YICHUANG_OCR_TEXT,
    )
    assert detail["registerAuthority"] == ""


def test_extract_approval_date_from_bottom_right() -> None:
    text = """
    成立日期2008年11月04日
    深圳市市场监督管理局
    2020年05月20日
    """
    assert extract_approval_date(text, "2008-11-04") == "2020-05-20"


def test_extract_registered_address_inline() -> None:
    text = "住所深圳市南山区粤海街道科技南十二路6号中检大厦1801成立日期2008年11月04日"
    assert extract_registered_address(text) == "深圳市南山区粤海街道科技南十二路6号中检大厦1801"


def test_extract_registered_address_strips_trailing_ocr_noise() -> None:
    text = (
        "住 所 深圳市罗湖区笋岗街道田心社区红岭北路2188号广田大厦27层重 "
        "o 登记机关 2026年 03月 ( 03日"
    )
    assert extract_registered_address(text) == (
        "深圳市罗湖区笋岗街道田心社区红岭北路2188号广田大厦27层"
    )


def test_extract_approval_date_from_seal_with_loose_ocr() -> None:
    seal_text = "深圳市市场监督管理局 2020年05月20日"
    assert extract_approval_date_from_seal(seal_text, "2008-11-04") == "2020-05-20"

    garbled = "登记机关 2026年 03月 ( 03日"
    assert extract_approval_date_from_seal(garbled, "2008-11-04") == "2026-03-03"


def test_extract_company_name_by_suffix() -> None:
    text = "统一社会信用代码\n91440300682024797J\n深圳市广田集团股份有限公司"
    assert extract_company_name(text) == "深圳市广田集团股份有限公司"
