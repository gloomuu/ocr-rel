from ocr_rel.llm.validator import normalize_detail
from ocr_rel.parsers.type3_audit_report import normalize_total_assets_yuan


def test_normalize_total_assets_yuan_plain() -> None:
    assert normalize_total_assets_yuan("25000000") == "25000000"
    assert normalize_total_assets_yuan("25,000,000.00") == "25000000"


def test_normalize_total_assets_yuan_from_wan() -> None:
    assert normalize_total_assets_yuan("2100", wan_unit=True) == "21000000"


def test_normalize_detail_type3() -> None:
    detail = normalize_detail(
        3,
        {
            "companyName": "河南测试售电有限公司",
            "accountingFirmName": "立信会计师事务所",
            "reportCode": "信会师报字[2023]第ZA12345号",
            "totalAssets": "2100万元",
        },
    )
    assert detail["totalAssets"] == "21000000"
