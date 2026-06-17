from __future__ import annotations

import re

CREDIT_CODE_PATTERN = re.compile(r"[0-9A-Z]{18}")
DATE_PATTERN = re.compile(r"(\d{4}[年\-/\.]\d{1,2}[月\-/\.]\d{1,2}日?)")
COMPANY_NAME_PATTERN = re.compile(
    r"([\u4e00-\u9fff（）()·]{2,60}"
    r"(?:有限责任公司|股份有限公司|有限公司|集团有限公司|合伙企业|个人独资企业|分公司))"
)
AUTHORITY_CORE_PATTERN = re.compile(r"([\u4e00-\u9fff]{2,12}市市场监督管理局)")
AUTHORITY_PATTERN = re.compile(
    r"([\u4e00-\u9fff]{2,12}(?:市场监督管理局|工商行政管理局|行政审批局|市监局|市场和质量监督管理委员会))"
)
AUTHORITY_DISTRICT_PATTERN = re.compile(
    r"([\u4e00-\u9fff]{2,12}[区县]市场监督管理局)"
)
AUTHORITY_LABEL_ONLY = frozenset({"登记机关", "发照机关", "机关"})
AUTHORITY_INVALID_WORDS = ("应向", "申请", "登记", "机关", "商事", "年度报告")
AUTHORITY_EXCLUDE_KEYWORDS = (
    "国家市场监督管理总局",
    "国家企业信用信息公示系统",
    "监制",
    "gsxt.gov.cn",
    "http",
    "https",
    "www.",
    "公示系统",
)
FOOTER_MARKERS = (
    "国家市场监督管理总局监制",
    "国家企业信用信息公示系统",
    "gsxt.gov.cn",
    "扫描二维码",
    "商事主体",
    "年度报告",
)
ADDRESS_HINT_PATTERN = re.compile(
    r"([\u4e00-\u9fff]{2,10}[省市区县].{4,100}?(?:号|室|层|幢|座|弄|路|街|大道|大厦|广场|中心|园区|小区))"
)

BUSINESS_LICENSE_LABELS: dict[str, list[str]] = {
    "companyName": ["名称", "企业名称", "公司名称"],
    "registeredAddress": ["住所", "注册地址", "住 所"],
    "establishDate": ["成立日期", "成立时间"],
    "registerAuthority": ["登记机关", "发照机关"],
    "approvalDate": ["核准日期", "发证日期"],
    "legalPerson": ["法定代表人", "负责人"],
    "businessScope": ["经营范围"],
    "registeredCapital": ["注册资本"],
    "companyType": ["类型", "类 型"],
}

ALL_FIELD_LABELS = sorted(
    {label for labels in BUSINESS_LICENSE_LABELS.values() for label in labels},
    key=len,
    reverse=True,
)

STOP_MARKERS = [
    "经营范围",
    "注册资本",
    "成立日期",
    "法定代表人",
    "负责人",
    "类型",
    "营业期限",
    "登记机关",
    "核准日期",
    "统一社会信用代码",
    "商事主体",
    "年度报告",
    "企业信息公示",
    "应向商事",
    "1.",
    "1、",
    "2.",
    "2、",
]

ADDRESS_STOP_LABELS = [
    "成立日期",
    "注册资本",
    "经营范围",
    "法定代表人",
    "负责人",
    "类型",
    "营业期限",
    "登记机关",
    "核准日期",
]


def normalize_spaces(text: str) -> str:
    return re.sub(r"\s+", "", text)


def split_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def format_chinese_date(value: str) -> str:
    normalized = (
        value.replace("年", "-")
        .replace("月", "-")
        .replace("日", "")
        .replace("/", "-")
        .replace(".", "-")
    )
    parts = [part for part in normalized.split("-") if part]
    if len(parts) >= 3:
        year, month, day = parts[0], parts[1].zfill(2), parts[2].zfill(2)
        return f"{year}-{month}-{day}"
    return value


def extract_credit_code(text: str) -> str | None:
    match = CREDIT_CODE_PATTERN.search(normalize_spaces(text.upper()))
    return match.group(0) if match else None


def _label_regex(label: str) -> str:
    chars = [re.escape(char) for char in label if not char.isspace()]
    return r"\s*".join(chars)


def _line_matches_label(line: str, labels: list[str]) -> bool:
    compact = normalize_spaces(line)
    for label in labels:
        label_re = _label_regex(label)
        if re.fullmatch(rf"{label_re}[:：]?", compact):
            return True
        if re.match(rf"^{label_re}[:：]", compact):
            return True
    return False


def _is_known_field_label(line: str) -> bool:
    compact = normalize_spaces(line)
    for label in ALL_FIELD_LABELS:
        label_re = _label_regex(label)
        if re.match(rf"^{label_re}[:：]?", compact):
            return True
    if compact.startswith("统一社会信用代码"):
        return True
    return False


def _trim_at_stop(value: str) -> str:
    trimmed = value.strip(" ：:;；")
    for marker in STOP_MARKERS:
        index = trimmed.find(marker)
        if index > 0:
            trimmed = trimmed[:index]
    trimmed = re.split(r"\s{2,}\d+[\.、]", trimmed)[0]
    return trimmed.strip(" ：:;；,.，。")


def _clean_address(value: str) -> str:
    cleaned = _trim_at_stop(value.strip())
    cleaned = re.sub(r"\s+", "", cleaned)
    for marker in ADDRESS_STOP_LABELS:
        index = cleaned.find(marker)
        if index > 0:
            cleaned = cleaned[:index]
    return cleaned.strip(" ，,。;；")


def _looks_like_address(value: str) -> bool:
    if len(value) < 8:
        return False
    if COMPANY_NAME_PATTERN.fullmatch(value):
        return False
    hints = ("省", "市", "区", "县", "路", "街", "号", "层", "道", "大厦", "广场", "街道", "社区")
    return sum(1 for hint in hints if hint in value) >= 2


def _is_valid_authority(value: str) -> bool:
    normalized = normalize_spaces(value)
    if len(normalized) < 6 or normalized in AUTHORITY_LABEL_ONLY:
        return False
    if any(keyword in normalized for keyword in AUTHORITY_EXCLUDE_KEYWORDS):
        return False
    for pattern in (AUTHORITY_CORE_PATTERN, AUTHORITY_DISTRICT_PATTERN, AUTHORITY_PATTERN):
        if pattern.fullmatch(normalized) or pattern.search(normalized):
            return True
    return any(keyword in normalized for keyword in ("管理局", "工商局", "行政审批局", "市监局"))


def is_invalid_register_authority(value: str) -> bool:
    normalized = normalize_spaces(value)
    if not normalized or normalized in AUTHORITY_LABEL_ONLY:
        return True
    if any(keyword in normalized for keyword in AUTHORITY_EXCLUDE_KEYWORDS):
        return True
    return not _is_valid_authority(normalized)


def _is_footer_line(line: str) -> bool:
    compact = normalize_spaces(line)
    if compact.startswith("登记机关") or compact.startswith("发照机关"):
        return False
    return any(marker in compact for marker in FOOTER_MARKERS)


def _trim_footer_suffix(text: str) -> str:
    trimmed = text
    for marker in FOOTER_MARKERS:
        index = trimmed.find(marker)
        if index > 0:
            trimmed = trimmed[:index]
    return trimmed.strip()


def _strip_authority_noise(value: str) -> str:
    cleaned = value.strip(" ：:;；,.，。()（）")
    cleaned = DATE_PATTERN.sub("", cleaned)
    cleaned = re.sub(r"[年月日\s]", "", cleaned)
    return cleaned.strip(" ：:;；,.，。()（）")


def _find_seal_area_start(lines: list[str]) -> int:
    for index in range(len(lines) - 1, -1, -1):
        line = lines[index]
        if _is_footer_line(line) or "应向" in normalize_spaces(line):
            continue
        compact = normalize_spaces(line)
        if _line_matches_label(line, BUSINESS_LICENSE_LABELS["registerAuthority"]):
            return index
        if compact.startswith("登记机关") or compact.startswith("发照机关"):
            return index
    return -1


def _extract_authority_from_line(line: str) -> str | None:
    compact = normalize_spaces(_trim_footer_suffix(line))
    if not compact or _is_footer_line(line):
        return None

    inline = _extract_inline_value(line, BUSINESS_LICENSE_LABELS["registerAuthority"])
    if inline:
        cleaned = _strip_authority_noise(_normalize_authority(inline))
        if _is_valid_authority(cleaned):
            return cleaned

    match = re.search(
        r"登记机关\s*([\u4e00-\u9fff]{2,30}?(?:市场监督管理局|行政审批局|工商行政管理局|市监局|工商局))",
        compact,
    )
    if match:
        cleaned = _strip_authority_noise(match.group(1))
        if _is_valid_authority(cleaned):
            return cleaned

    for pattern in (AUTHORITY_CORE_PATTERN, AUTHORITY_DISTRICT_PATTERN, AUTHORITY_PATTERN):
        match = pattern.search(compact)
        if match:
            cleaned = _strip_authority_noise(match.group(1))
            if _is_valid_authority(cleaned):
                return cleaned
    return None


def _authority_patterns() -> tuple[re.Pattern[str], ...]:
    return (AUTHORITY_CORE_PATTERN, AUTHORITY_DISTRICT_PATTERN, AUTHORITY_PATTERN)


def _extract_authority_from_bottom_region(text: str) -> str | None:
    footer_index = len(text)
    for marker in FOOTER_MARKERS:
        index = text.find(marker)
        if index > 0:
            footer_index = min(footer_index, index)

    bottom = text[:footer_index]
    seal_start = bottom.rfind("登记机关")
    region = bottom[seal_start:] if seal_start >= 0 else bottom[-400:]
    region = _trim_footer_suffix(normalize_spaces(region))

    for pattern in _authority_patterns():
        match = pattern.search(region)
        if match:
            cleaned = _strip_authority_noise(match.group(1))
            if _is_valid_authority(cleaned):
                return cleaned
    return None


def _extract_authority_from_trailing_lines(text: str, *, max_lines: int = 6) -> str | None:
    lines = split_lines(text)
    for line in reversed(lines[-max_lines:]):
        if _is_footer_line(line):
            continue
        authority = _extract_authority_from_line(line)
        if authority:
            return authority
    return None


def _extract_authority_from_seal_area(text: str) -> str | None:
    lines = split_lines(text)
    seal_start = _find_seal_area_start(lines)
    if seal_start < 0:
        return None

    window = lines[seal_start : min(seal_start + 4, len(lines))]
    for line in window:
        if _is_footer_line(line):
            continue
        authority = _extract_authority_from_line(line)
        if authority:
            return authority

    merged = normalize_spaces("".join(window))
    match = re.search(
        r"登记机关([\u4e00-\u9fff]{2,30}?(?:市场监督管理局|行政审批局|工商行政管理局|市监局|工商局))",
        merged,
    )
    if match:
        cleaned = _strip_authority_noise(match.group(1))
        if _is_valid_authority(cleaned):
            return cleaned
    return None


def _extract_inline_value(line: str, labels: list[str]) -> str | None:
    compact = normalize_spaces(line)
    for label in labels:
        label_re = _label_regex(label)
        match = re.match(rf"^{label_re}[:：]?\s*(.+)$", compact)
        if match:
            value = match.group(1).strip()
            return _trim_at_stop(value) if value else None
    return None


def extract_labeled_field(text: str, labels: list[str], *, multiline: bool = False) -> str | None:
    lines = split_lines(text)

    for index, line in enumerate(lines):
        inline_value = _extract_inline_value(line, labels)
        if inline_value:
            return inline_value

        if _line_matches_label(line, labels):
            if not multiline:
                next_index = index + 1
                if next_index < len(lines) and not _is_known_field_label(lines[next_index]):
                    return _trim_at_stop(lines[next_index])
                continue

            parts: list[str] = []
            for next_index in range(index + 1, len(lines)):
                candidate = lines[next_index]
                if _is_known_field_label(candidate):
                    break
                if any(marker in candidate for marker in ("商事主体", "年度报告", "企业信息公示", "应向商事")):
                    break
                if re.match(r"^\d+[\.、]", candidate):
                    break
                parts.append(candidate)
            if parts:
                return _trim_at_stop("".join(parts))
    return None


def extract_date_near_label(text: str, labels: list[str]) -> str | None:
    lines = split_lines(text)
    for index, line in enumerate(lines):
        compact = normalize_spaces(line)
        for label in labels:
            label_re = _label_regex(label)
            if re.search(label_re, compact):
                match = DATE_PATTERN.search(line)
                if match:
                    return format_chinese_date(match.group(1))
                for next_index in range(index + 1, min(index + 4, len(lines))):
                    match = DATE_PATTERN.search(lines[next_index])
                    if match:
                        return format_chinese_date(match.group(1))
    match = re.search(
        rf"(?:{'|'.join(_label_regex(label) for label in labels)})[:：]?\s*"
        rf"({DATE_PATTERN.pattern})",
        normalize_spaces(text),
    )
    if match:
        return format_chinese_date(match.group(1))
    return None


def extract_all_dates(text: str) -> list[str]:
    dates: list[str] = []
    seen: set[str] = set()
    for match in DATE_PATTERN.finditer(text):
        formatted = format_chinese_date(match.group(1))
        if formatted not in seen:
            seen.add(formatted)
            dates.append(formatted)
    return dates


def extract_registered_address(text: str) -> str | None:
    labels = BUSINESS_LICENSE_LABELS["registeredAddress"]

    labeled = extract_labeled_field(text, labels, multiline=True)
    if labeled:
        cleaned = _clean_address(labeled)
        if _looks_like_address(cleaned):
            return cleaned

    flattened = " ".join(split_lines(text))
    inline_patterns = [
        r"住\s*所[:：]?\s*([\u4e00-\u9fff0-9A-Za-z（）()·\-—#,.，。\s]{8,120}?)"
        r"(?=成立日期|注册资本|经营范围|法定代表人|负责人|类型|营业期限|登记机关|核准日期|$)",
        r"住\s*所[:：]?\s*([^\n]{8,120})",
    ]
    for pattern in inline_patterns:
        match = re.search(pattern, flattened)
        if match:
            cleaned = _clean_address(match.group(1))
            if _looks_like_address(cleaned):
                return cleaned

    compact = normalize_spaces(flattened)
    match = re.search(
        r"住所[:：]?"
        r"([\u4e00-\u9fff0-9A-Za-z（）()·#\-—]+?(?:号|层|室|幢|座|弄|组|队|社|大厦|广场|中心|小区|园区|路|街|道))"
        r"(?:\d+[层室号幢座])?",
        compact,
    )
    if match:
        cleaned = _clean_address(match.group(1))
        if _looks_like_address(cleaned):
            return cleaned

    match = ADDRESS_HINT_PATTERN.search(compact)
    if match:
        cleaned = _clean_address(match.group(1))
        if _looks_like_address(cleaned):
            return cleaned

    best: str | None = None
    for line in split_lines(text):
        if _is_known_field_label(line):
            continue
        if COMPANY_NAME_PATTERN.search(line):
            continue
        cleaned = _clean_address(line)
        if _looks_like_address(cleaned) and (best is None or len(cleaned) > len(best)):
            best = cleaned
    return best


def extract_approval_date(text: str, establish_date: str | None = None) -> str | None:
    labeled = extract_date_near_label(text, BUSINESS_LICENSE_LABELS["approvalDate"])
    if labeled and labeled != establish_date:
        return labeled

    lines = split_lines(text)
    for index in range(len(lines) - 1, -1, -1):
        line = lines[index]
        if AUTHORITY_PATTERN.search(line) or "登记机关" in normalize_spaces(line):
            for next_index in range(index, min(index + 4, len(lines))):
                match = DATE_PATTERN.search(lines[next_index])
                if match:
                    formatted = format_chinese_date(match.group(1))
                    if formatted != establish_date:
                        return formatted
            break

    for line in reversed(lines[-8:]):
        match = DATE_PATTERN.search(line)
        if match:
            formatted = format_chinese_date(match.group(1))
            if formatted != establish_date:
                return formatted

    dates = extract_all_dates(text)
    if establish_date and establish_date in dates:
        dates = [item for item in dates if item != establish_date]
    if dates:
        return dates[-1]
    return None


def extract_company_name(text: str) -> str | None:
    labeled = extract_labeled_field(text, BUSINESS_LICENSE_LABELS["companyName"])
    if labeled and len(labeled) >= 4:
        return labeled

    match = COMPANY_NAME_PATTERN.search(text.replace("\n", ""))
    if match:
        return match.group(1).strip()

    for line in split_lines(text):
        if "公司" in line or "企业" in line:
            cleaned = re.sub(r"^(名称|企业名称|公司名称)[:：]?\s*", "", line).strip()
            if 4 <= len(cleaned) <= 60 and "经营范围" not in cleaned:
                return cleaned
    return None


def _normalize_authority(value: str) -> str:
    return value.replace("登记机关", "").strip()


def _collect_authority_candidates(text: str) -> list[str]:
    seal_authority = _extract_authority_from_seal_area(text)
    if seal_authority:
        return [seal_authority]

    trailing_authority = _extract_authority_from_trailing_lines(text)
    if trailing_authority:
        return [trailing_authority]

    bottom_authority = _extract_authority_from_bottom_region(text)
    if bottom_authority:
        return [bottom_authority]

    lines = split_lines(text)
    candidates: list[str] = []

    for line in reversed(lines):
        if _is_footer_line(line) or "应向" in normalize_spaces(line):
            continue
        if DATE_PATTERN.search(line):
            authority = _extract_authority_from_line(line)
            if authority:
                candidates.append(authority)

    for index, line in enumerate(lines):
        if not _line_matches_label(line, BUSINESS_LICENSE_LABELS["registerAuthority"]):
            continue
        for next_index in range(index + 1, min(index + 3, len(lines))):
            next_line = lines[next_index]
            if _is_footer_line(next_line) or "应向" in normalize_spaces(next_line):
                break
            authority = _extract_authority_from_line(next_line)
            if authority:
                candidates.append(authority)

    deduped: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        cleaned = _normalize_authority(candidate)
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            deduped.append(cleaned)
    return deduped


def extract_register_authority(text: str) -> str | None:
    candidates = [item for item in _collect_authority_candidates(text) if _is_valid_authority(item)]
    valid = [item for item in candidates if not any(word in item for word in AUTHORITY_INVALID_WORDS)]
    if valid:
        return valid[0]
    return None
