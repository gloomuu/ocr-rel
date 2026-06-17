import pytest
from PIL import Image

from ocr_rel.parsers.type3_audit_report import (
    extract_cover_fields,
    extract_total_assets_from_balance_sheet,
    is_balance_sheet_page,
)
from ocr_rel.services.audit_report_ocr import recognize_audit_report_detail


YICHUANG_COVER_TEXT = """
深圳壹创国际设计股份有限公司
二〇二四年度
审计报告
致同会计师事务所 (特殊普通合伙)
此码用于证明该审计报告是否由具有执业许可的会计师事务所出具
报告编码：京25CLW5B6TX
"""

COVER_TEXT = """
审计报告
被审计单位：河南测试售电有限公司
会计师事务所：立信会计师事务所（特殊普通合伙）河南分所
报告文号：信会师报字[2023]第ZA12345号
我们审计了河南测试售电有限公司财务报表
"""

BALANCE_SHEET_TEXT = """
资产负债表
期末余额 期初余额
流动资产 100 90
非流动资产 200 180
资产总计 25000000 20000000
负债和所有者权益
"""

IRRELEVANT_PAGE_TEXT = "附注 一、公司基本情况 说明文字"

TOC_PAGE_TEXT = """
目录
一、审计报告 1
二、合并及公司资产负债表 1-2
三、合并及公司利润表 3
期末余额
"""

FALSE_BALANCE_PAGE_TEXT = """
合并及公司资产负债表
期末余额 期初余额
二〇二四年度
资产总计 2024 2023
"""

CONSOLIDATED_BALANCE_SHEET_COMPANY_FIRST = """
合并及公司资产负债表
期末余额 期初余额
公司 合并 公司 合并
流动资产 100 200 90 180
资产总计 37974702.95 188364096.84 35000000 150000000
负债和所有者权益
"""

CONSOLIDATED_BALANCE_SHEET_MERGE_FIRST = """
合并及公司资产负债表
期末余额 期初余额
合并 公司 合并 公司
资产总计 188364096.84 37974702.95 150000000 35000000
"""

# 阿里云 OCR 将整页识别为单行时的真实片段（深圳壹创 page 8）
REAL_OCR_SINGLE_LINE_PAGE = (
    "合并及公司资产负债表 2024年12月31日 编制单位：深圳壹创国际设计股份有限公司 单位：人民币元 "
    "期末余额 上年年末余额 项 目 附注 合并 公司 合并 公司 流动资产： "
    "货币资金 37，974，702.95 35，739，875.71 35，798，512.60 33，835，008.64 "
    "流动资产合计 151，099，627.43 161，760，554.66 154，118，733.72 158，678，527.84 "
    "非流动资产合计 37，264，469.41 45，670，497.99 32，579，172.63 39，916，875.02 "
    "资产总计 188，364，096.84 207，431，052.65 186，697，906.35 198，595，402.86"
)


class FakeAuditOcrEngine:
    def __init__(self, pages: list[str]) -> None:
        self._pages = pages
        self._index = 0

    async def recognize_image(self, image: Image.Image) -> str:
        if self._index >= len(self._pages):
            return ""
        text = self._pages[self._index]
        self._index += 1
        return text


class FakeAuditLlmExtractor:
    is_available = True

    def __init__(
        self,
        total_assets: str = "25000000",
        *,
        cover_fields: dict[str, str] | None = None,
        require_in_text: bool = False,
    ) -> None:
        self._total_assets = total_assets
        self._cover_fields = cover_fields or {
            "companyName": "河南测试售电有限公司",
            "accountingFirmName": "立信会计师事务所（特殊普通合伙）河南分所",
            "reportCode": "信会师报字[2023]第ZA12345号",
        }
        self._require_in_text = require_in_text
        self.calls: list[str] = []
        self.cover_calls: list[str] = []

    async def extract_cover_fields(self, cover_text: str) -> dict[str, str]:
        self.cover_calls.append(cover_text)
        return dict(self._cover_fields)

    async def extract_total_assets(self, balance_sheet_text: str) -> str:
        self.calls.append(balance_sheet_text)
        if self._require_in_text:
            compact = balance_sheet_text.replace(",", "").replace("，", "")
            if self._total_assets not in compact:
                raise ValueError("LLM mock: totalAssets not found in page")
        return self._total_assets


def test_extract_cover_fields() -> None:
    detail = extract_cover_fields(COVER_TEXT)
    assert detail["companyName"] == "河南测试售电有限公司"
    assert "立信会计师事务所" in detail["accountingFirmName"]
    assert detail["reportCode"] == "信会师报字[2023]第ZA12345号"
    assert detail["totalAssets"] == ""


def test_extract_cover_fields_rejects_disclaimer_as_firm_name() -> None:
    from ocr_rel.parsers.type3_audit_report import extract_accounting_firm_name

    firm = extract_accounting_firm_name(YICHUANG_COVER_TEXT)
    assert firm is not None
    assert "致同会计师事务所" in firm
    assert "此码用于证明" not in firm


def test_extract_report_code_from_encoding_label() -> None:
    from ocr_rel.parsers.type3_audit_report import extract_report_code

    text = "报告编码：京25CLW5B6TX"
    assert extract_report_code(text) == "京25CLW5B6TX"


def test_is_balance_sheet_page() -> None:
    assert is_balance_sheet_page(BALANCE_SHEET_TEXT) is True
    assert is_balance_sheet_page(COVER_TEXT) is False
    assert is_balance_sheet_page(TOC_PAGE_TEXT) is False


def test_extract_total_assets_rejects_year_like_values() -> None:
    assert extract_total_assets_from_balance_sheet(FALSE_BALANCE_PAGE_TEXT) is None


def test_extract_total_assets_from_consolidated_balance_sheet_company_first() -> None:
    assets = extract_total_assets_from_balance_sheet(CONSOLIDATED_BALANCE_SHEET_COMPANY_FIRST)
    assert assets == "188364096.84"


def test_extract_total_assets_from_consolidated_balance_sheet_merge_first() -> None:
    assets = extract_total_assets_from_balance_sheet(CONSOLIDATED_BALANCE_SHEET_MERGE_FIRST)
    assert assets == "188364096.84"


def test_extract_total_assets_from_real_ocr_single_line_page() -> None:
    assets = extract_total_assets_from_balance_sheet(REAL_OCR_SINGLE_LINE_PAGE)
    assert assets == "188364096.84"


def test_extract_total_assets_from_balance_sheet() -> None:
    assets = extract_total_assets_from_balance_sheet(BALANCE_SHEET_TEXT)
    assert assets == "25000000"


@pytest.mark.asyncio
async def test_recognize_audit_report_uses_llm_on_cover_page() -> None:
    llm = FakeAuditLlmExtractor(
        cover_fields={
            "companyName": "深圳壹创国际设计股份有限公司",
            "accountingFirmName": "致同会计师事务所(特殊普通合伙)",
            "reportCode": "京25CLW5B6TX",
        }
    )
    engine = FakeAuditOcrEngine([YICHUANG_COVER_TEXT])

    detail, _ = await recognize_audit_report_detail(engine, [Image.new("RGB", (1, 1))], llm_extractor=llm)
    assert detail["companyName"] == "深圳壹创国际设计股份有限公司"
    assert detail["accountingFirmName"] == "致同会计师事务所(特殊普通合伙)"
    assert detail["reportCode"] == "京25CLW5B6TX"
    assert len(llm.cover_calls) == 1


@pytest.mark.asyncio
async def test_recognize_audit_report_stops_after_balance_sheet() -> None:
    llm = FakeAuditLlmExtractor("25000000")
    engine = FakeAuditOcrEngine([COVER_TEXT, IRRELEVANT_PAGE_TEXT, BALANCE_SHEET_TEXT, "不应再 OCR"])
    images = [Image.new("RGB", (100, 100), color=(255, 255, 255)) for _ in range(4)]

    detail, cover_text = await recognize_audit_report_detail(engine, images, llm_extractor=llm)
    assert cover_text.strip().startswith("审计报告")
    assert detail["companyName"] == "河南测试售电有限公司"
    assert detail["totalAssets"] == "25000000"
    assert engine._index == 3
    assert len(llm.calls) == 1
    assert "资产总计" in llm.calls[0]


@pytest.mark.asyncio
async def test_recognize_audit_report_uses_llm_on_balance_sheet_page() -> None:
    llm = FakeAuditLlmExtractor("188364096.84")
    engine = FakeAuditOcrEngine([COVER_TEXT, REAL_OCR_SINGLE_LINE_PAGE])
    images = [Image.new("RGB", (100, 100), color=(255, 255, 255)) for _ in range(2)]

    detail, _ = await recognize_audit_report_detail(engine, images, llm_extractor=llm)
    assert detail["totalAssets"] == "188364096.84"
    assert len(llm.calls) == 1


@pytest.mark.asyncio
async def test_recognize_audit_report_skips_until_balance_sheet() -> None:
    llm = FakeAuditLlmExtractor()
    engine = FakeAuditOcrEngine([COVER_TEXT, IRRELEVANT_PAGE_TEXT, BALANCE_SHEET_TEXT])
    images = [Image.new("RGB", (100, 100), color=(255, 255, 255)) for _ in range(3)]

    detail, _ = await recognize_audit_report_detail(engine, images, llm_extractor=llm)
    assert detail["totalAssets"] == "25000000"
    assert engine._index == 3


@pytest.mark.asyncio
async def test_recognize_audit_report_skips_toc_and_false_balance_page() -> None:
    llm = FakeAuditLlmExtractor(require_in_text=True)
    engine = FakeAuditOcrEngine(
        [COVER_TEXT, TOC_PAGE_TEXT, FALSE_BALANCE_PAGE_TEXT, BALANCE_SHEET_TEXT, "不应再 OCR"]
    )
    images = [Image.new("RGB", (100, 100), color=(255, 255, 255)) for _ in range(5)]

    detail, _ = await recognize_audit_report_detail(engine, images, llm_extractor=llm)
    assert detail["totalAssets"] == "25000000"
    assert engine._index == 4
    assert len(llm.calls) == 2
