from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from ocr_rel.parsers.base import BaseParser
from ocr_rel.parsers.text_utils import extract_company_name, extract_labeled_field, split_lines

TOTAL_ASSETS_LABELS = [
    "资产总额",
    "资产总计",
    "总资产",
    "期末资产总额",
    "资产合计",
    "资产总额合计",
]

COMPANY_LABELS = [
    "被审计单位",
    "客户名称",
    "单位名称",
    "公司名称",
    "企业名称",
]

FIRM_LABELS = [
    "会计师事务所",
    "审计机构",
    "执行审计机构",
]

REPORT_CODE_LABELS = [
    "报告编码",
    "报告文号",
    "报告编号",
    "审计报告文号",
    "文号",
]

# 行业监管平台编码，可能含中文前缀，如：京25CLW5B6TX
REPORT_CODE_INLINE_PATTERN = re.compile(
    r"报告编码[:：]?\s*([A-Za-z0-9\u4e00-\u9fff]{6,32})"
)
AUDIT_REPORT_NO_PATTERN = re.compile(
    r"([\u4e00-\u9fff]{2,10}审字[\(（]?\d{4}[\)）]?第[A-Za-z0-9]+号)"
)
FIRM_NAME_PATTERN = re.compile(
    r"([\u4e00-\u9fff（）()·\s]{2,50}(?:会计师事务所|注册会计师事务所有限公司|审计事务所)"
    r"(?:[\(（][^)）]{2,30}[\)）])?)"
)
REPORT_CODE_PATTERN = re.compile(
    r"([\u4e00-\u9fff0-9A-Za-z（）()\[\]【】〔〕\-—_·]{6,40}"
    r"(?:号|字|审|报|第[\d]+号))"
)
TOTAL_ASSETS_ROW_LABEL_PATTERN = re.compile(
    r"(?<!流动)(?<!非流动)资产总计|(?<!流动)(?<!非流动)资产总额"
)
# 兼容旧引用；仅匹配真正的「资产总计/资产总额」行，不含流动/非流动资产合计
TOTAL_ASSETS_ROW_PATTERN = TOTAL_ASSETS_ROW_LABEL_PATTERN
TOC_PATTERN = re.compile(r"目\s*录")
LIABILITY_SECTION_PATTERN = re.compile(r"负债和(?:股东|所有者)|负债及所有者")


def extract_audit_company_name(text: str) -> str | None:
    labeled = extract_labeled_field(text, COMPANY_LABELS)
    if labeled and len(labeled) >= 4:
        cleaned = _trim_company_noise(labeled)
        if cleaned and "会计师事务所" not in cleaned:
            return cleaned

    match = re.search(
        r"被审计单位[:：]?\s*([\u4e00-\u9fff（）()·]{4,60}"
        r"(?:有限责任公司|股份有限公司|有限公司|集团有限公司|公司|企业))",
        text,
    )
    if match:
        return _trim_company_noise(match.group(1))

    company = extract_company_name(text)
    if company and "会计师事务所" not in company:
        return company
    return None


INVALID_ACCOUNTING_FIRM_MARKERS = (
    "此码用于证明",
    "执业许可",
    "扫一扫",
    "统一监管平台",
    "统一临管平台",
    "查验",
    "注册会计师行业",
)


def is_invalid_accounting_firm_name(value: str) -> bool:
    if not value or not value.strip():
        return True
    compact = value.strip()
    if any(marker in compact for marker in INVALID_ACCOUNTING_FIRM_MARKERS):
        return True
    if "会计师事务所" not in compact and "审计事务所" not in compact:
        return True
    if len(compact) > 80:
        return True
    return False
def extract_accounting_firm_name(text: str) -> str | None:
    labeled = extract_labeled_field(text, FIRM_LABELS)
    if labeled:
        cleaned = _trim_firm_noise(labeled)
        if cleaned and not is_invalid_accounting_firm_name(cleaned):
            return _normalize_firm_name(cleaned)

    best: str | None = None
    for match in FIRM_NAME_PATTERN.finditer(text.replace("\n", " ")):
        candidate = _normalize_firm_name(match.group(1))
        if candidate and is_invalid_accounting_firm_name(candidate):
            continue
        if candidate and (best is None or len(candidate) > len(best)):
            best = candidate
    if best:
        return best

    for line in text.splitlines():
        compact = re.sub(r"\s+", "", line)
        if "会计师事务所" not in compact and "审计事务所" not in compact:
            continue
        if len(compact) > 60 or is_invalid_accounting_firm_name(compact):
            continue
        return _normalize_firm_name(compact)
    return None


def extract_report_code(text: str) -> str | None:
    flattened = text.replace("\n", " ")

    inline_encoding = REPORT_CODE_INLINE_PATTERN.search(flattened)
    if inline_encoding:
        return _clean_report_code(inline_encoding.group(1))

    labeled = extract_labeled_field(text, REPORT_CODE_LABELS)
    if labeled:
        cleaned = _clean_report_code(labeled)
        if len(cleaned) >= 4:
            return cleaned

    audit_no_match = AUDIT_REPORT_NO_PATTERN.search(flattened.replace(" ", ""))
    if audit_no_match:
        return audit_no_match.group(1).strip()

    match = REPORT_CODE_PATTERN.search(flattened)
    if match:
        return match.group(1).strip()
    return None


def extract_cover_fields(text: str) -> dict[str, str]:
    return {
        "companyName": extract_audit_company_name(text) or "",
        "accountingFirmName": extract_accounting_firm_name(text) or "",
        "reportCode": extract_report_code(text) or "",
        "totalAssets": "",
    }


def is_balance_sheet_page(text: str) -> bool:
    """仅当页面同时含「资产负债」与「期末余额」时，才视为资产负债表页并提取 totalAssets。"""
    if "资产负债" not in text or "期末余额" not in text:
        return False
    # 目录页会提到「资产负债表」，但没有资产总计行
    if TOC_PATTERN.search(text) and not TOTAL_ASSETS_ROW_PATTERN.search(text):
        return False
    return True


def _find_last_total_assets_match(text: str) -> re.Match[str] | None:
    matches = list(TOTAL_ASSETS_ROW_LABEL_PATTERN.finditer(text))
    return matches[-1] if matches else None


def _extract_balance_sheet_header(text: str) -> str:
    last_match = _find_last_total_assets_match(text)
    if last_match:
        return text[: last_match.start()]

    header_lines: list[str] = []
    for line in split_lines(text):
        if TOTAL_ASSETS_ROW_LABEL_PATTERN.search(line):
            break
        if any(
            keyword in line
            for keyword in ("期末余额", "期初余额", "上年年末余额", "合并", "公司", "资产负债表")
        ):
            header_lines.append(line)
    return "\n".join(header_lines)


def _merged_column_index_in_ending_balance(header: str) -> int:
    """Return 0-based index of the 合并 column within the 期末余额 amount group."""
    if "合并" not in header:
        return 0

    compact = re.sub(r"\s+", "", header)
    ending_pos = compact.find("期末余额")
    search_from = ending_pos if ending_pos >= 0 else 0
    tokens = re.findall(r"合并|公司", compact[search_from:])
    if len(tokens) >= 2:
        return 0 if tokens[0] == "合并" else 1

    for line in split_lines(header):
        line_compact = re.sub(r"\s+", "", line)
        if any(
            keyword in line_compact
            for keyword in ("资产负债表", "期末余额", "期初余额", "上年年末余额")
        ):
            continue
        line_tokens = re.findall(r"合并|公司", line_compact)
        if len(line_tokens) >= 2:
            return 0 if line_tokens[0] == "合并" else 1

    return 0


def _extract_amounts_after_total_assets_label(segment: str) -> list[str]:
    label_match = TOTAL_ASSETS_ROW_LABEL_PATTERN.search(segment)
    if not label_match:
        return []

    after_label = segment[label_match.end() :]
    liability_match = LIABILITY_SECTION_PATTERN.search(after_label)
    if liability_match:
        after_label = after_label[: liability_match.start()]

    amounts: list[str] = []
    for raw_amount in re.findall(r"[\d,，]+(?:\.\d+)?", after_label):
        normalized = normalize_total_assets_yuan(raw_amount)
        if normalized:
            amounts.append(normalized)
    return amounts


def _extract_row_amounts(line: str) -> list[str]:
    return _extract_amounts_after_total_assets_label(line)


def extract_total_assets_from_balance_sheet(text: str) -> str | None:
    if not is_balance_sheet_page(text):
        return None

    last_match = _find_last_total_assets_match(text)
    if not last_match:
        return None

    header = text[: last_match.start()]
    col_index = _merged_column_index_in_ending_balance(header)
    segment = text[last_match.start() :]
    amounts = _extract_amounts_after_total_assets_label(segment)
    if amounts:
        return amounts[min(col_index, len(amounts) - 1)]
    return None


def normalize_total_assets_yuan(raw: str, *, wan_unit: bool = False) -> str | None:
    if not raw:
        return None
    compact = raw.replace(",", "").replace("，", "").strip()
    if not compact:
        return None

    if wan_unit or compact.endswith("万"):
        compact = compact.rstrip("万").strip()

    try:
        amount = Decimal(compact)
    except InvalidOperation:
        match = re.search(r"([\d.]+)", compact)
        if not match:
            return None
        try:
            amount = Decimal(match.group(1))
        except InvalidOperation:
            return None

    if wan_unit or "万" in raw:
        amount *= Decimal("10000")

    if not _is_plausible_total_assets(amount):
        return None

    if amount == amount.to_integral_value():
        return str(int(amount))
    return format(amount.normalize(), "f").rstrip("0").rstrip(".")


def _is_plausible_total_assets(amount: Decimal) -> bool:
    if amount <= 0:
        return False
    if amount == amount.to_integral_value():
        integer = int(amount)
        if 1900 <= integer <= 2100:
            return False
        if integer < 10000:
            return False
    return True


def _clean_report_code(value: str) -> str:
    return value.strip(" ：:;；,.，。()（）")


def _normalize_firm_name(value: str) -> str:
    cleaned = re.sub(r"\s+", "", value.strip())
    return cleaned.strip(" ：:;；,.，。")


def _extract_amount_near_label(text: str, label: str) -> str | None:
    label_chars = [re.escape(char) for char in label if not char.isspace()]
    label_re = r"\s*".join(label_chars)
    patterns = [
        rf"{label_re}[:：]?\s*([\d,，]+(?:\.\d+)?)\s*(万)?\s*元?",
        rf"{label_re}[:：]?\s*RMB\s*([\d,，]+(?:\.\d+)?)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            wan = bool(match.group(2)) if match.lastindex and match.lastindex >= 2 else False
            value = match.group(1)
            normalized = normalize_total_assets_yuan(value, wan_unit=wan)
            if normalized:
                return normalized
    return None


def extract_total_assets(text: str) -> str | None:
    for label in TOTAL_ASSETS_LABELS:
        inline = _extract_amount_near_label(text, label)
        if inline:
            return inline

    if is_balance_sheet_page(text):
        return extract_total_assets_from_balance_sheet(text)

    patterns = [
        r"资产(?:总额|总计|合计)[:：]?\s*([\d,，]+(?:\.\d+)?)\s*(万)?\s*元?",
        r"总资产[:：]?\s*([\d,，]+(?:\.\d+)?)\s*(万)?\s*元?",
    ]
    compact = re.sub(r"\s+", " ", text)
    for pattern in patterns:
        match = re.search(pattern, compact)
        if match:
            normalized = normalize_total_assets_yuan(match.group(1), wan_unit=bool(match.group(2)))
            if normalized:
                return normalized
    return None


def _trim_company_noise(value: str) -> str:
    trimmed = value.strip(" ：:;；,.，。")
    for marker in ("会计师事务所", "审计机构", "报告文号", "报告编码", "资产总额"):
        index = trimmed.find(marker)
        if index > 0:
            trimmed = trimmed[:index]
    return trimmed.strip(" ：:;；,.，。")


def _trim_firm_noise(value: str) -> str:
    trimmed = value.strip(" ：:;；,.，。")
    for marker in ("被审计单位", "资产总额", "报告文号", "报告编码"):
        index = trimmed.find(marker)
        if index > 0:
            trimmed = trimmed[:index]
    return trimmed.strip(" ：:;；,.，。")


class AuditReportParser(BaseParser):
    doc_type = 3

    def parse(
        self,
        text: str,
        personnel: str | None = None,
        attachment_name: str | None = None,
    ) -> dict[str, Any]:
        detail = extract_cover_fields(text)
        if is_balance_sheet_page(text):
            assets = extract_total_assets_from_balance_sheet(text)
            if assets:
                detail["totalAssets"] = assets
        elif not detail["totalAssets"]:
            legacy_assets = extract_total_assets(text)
            if legacy_assets:
                detail["totalAssets"] = legacy_assets
        return detail
