from __future__ import annotations

from typing import Any

DOCUMENT_FIELD_SCHEMAS: dict[int, dict[str, str]] = {
    1: {
        "unifiedSocialCreditCode": "统一社会信用代码，18位字母数字",
        "companyName": "企业名称",
        "establishDate": "成立日期，格式 YYYY-MM-DD",
        "registeredAddress": "住所/注册地址",
        "registerAuthority": "登记机关红色公章内的机关名称（如“深圳市市场监督管理局”），“登记机关”只是字段标题不是值，禁止输出标题本身或页脚监制单位",
        "approvalDate": "核准日期，格式 YYYY-MM-DD，通常在证照右下角",
    },
    2: {
        "name": "姓名",
        "idCardNumber": "身份证号码，18位",
    },
    3: {
        "companyName": "被审计单位/客户名称（售电公司名称）",
        "accountingFirmName": "出具报告的会计师事务所名称",
        "reportCode": "审计报告编码、报告文号或报告编号",
        "totalAssets": "资产总额，单位为元（人民币），输出纯数字字符串，不含单位；原文为万元需换算为元",
    },
    4: {
        "companyName": "被验资单位/公司名称（售电公司名称）",
        "accountingFirmName": "出具报告的会计师事务所名称",
        "reportCode": "验资报告文号、报告编码或报告编号",
    },
    5: {
        "name": "姓名",
        "idCardNumber": "身份证号码，18位",
    },
    6: {
        "copyrightOwner": "软件著作权证书的著作权人/权利人（企业全称），仅软著证书填写",
        "companyName": "等级保护备案证明的单位名称，仅等保备案填写",
        "systemLevel": "等级保护备案的安全保护等级，输出一级/二级/三级/四级/五级，仅等保备案填写",
    },
}

DOCUMENT_TYPE_NAMES: dict[int, str] = {
    1: "营业执照",
    2: "法人身份证",
    3: "审计报告",
    4: "验资报告",
    5: "从业人员身份证",
    6: "等级保护备案/软件著作权",
}


def get_field_schema(doc_type: int) -> dict[str, str]:
    schema = DOCUMENT_FIELD_SCHEMAS.get(doc_type)
    if schema is None:
        raise ValueError(f"No LLM field schema for document type {doc_type}")
    return schema


def build_system_prompt(doc_type: int) -> str:
    doc_name = DOCUMENT_TYPE_NAMES.get(doc_type, f"type-{doc_type}")
    fields = get_field_schema(doc_type)
    field_lines = "\n".join(f'- "{key}": {desc}' for key, desc in fields.items())
    keys = ", ".join(f'"{key}"' for key in fields)

    type_rules: list[str] = []
    if doc_type == 1:
        type_rules.extend(
            [
                "4. 忽略营业执照底部脚注（如“商事主体”“年度报告”“国家市场监督管理总局监制”等说明文字）。",
                "5. registerAuthority 只取右下角红色公章内的机关名称；“登记机关”是印刷标题不是答案，禁止输出；禁止取页脚监制单位。",
            ]
        )
    elif doc_type == 3:
        type_rules.extend(
            [
                "4. 首页仅提取 companyName、accountingFirmName、reportCode。",
                "5. totalAssets 仅来自含“资产负债”和“期末余额”的资产负债表页，取“资产总计”行在“期末余额”下“合并”列的金额，单位为元；无“合并”列时取第一个期末余额金额。",
            ]
        )
    elif doc_type == 4:
        type_rules.extend(
            [
                "4. companyName 取被验资单位/公司名称（售电公司），不要取会计师事务所名称。",
                "5. accountingFirmName 必须是出具验资报告的会计师事务所全称。",
                "6. reportCode 优先取封面「报告编码」；若无报告编码，再取验资报告文号（如「XX验字(2023)第XXX号」）。",
            ]
        )
    elif doc_type == 5:
        type_rules.extend(
            [
                "4. 从居民身份证 OCR 文本提取姓名与身份证号码。",
                "5. 若提供了 personnel 人员标识，不要在 JSON 中输出 personnel 字段（由系统另行透传）。",
            ]
        )
    elif doc_type == 6:
        type_rules.extend(
            [
                "4. type=6 在业务侧包含两类材料：等保备案与软著证书；系统会按 OCR 关键词分流处理，此处为通用兜底规则。",
                "5. 等保备案：通读全文提取 companyName 与 systemLevel。",
                "6. 软著证书：仅从首页提取 copyrightOwner。",
            ]
        )

    type_rules_text = "\n".join(type_rules)
    common_rules = """1. 只提取 OCR 文本中明确出现的信息，禁止猜测、补全或编造。
2. 找不到的字段必须输出空字符串 ""，不要输出 null。
3. 日期统一为 YYYY-MM-DD；原文为中文日期请转换。"""

    return f"""你是售电公司注册资料识别系统的结构化抽取助手。
任务：从 OCR 识别的{doc_name}文本中，提取指定字段并输出 JSON。

严格要求：
{common_rules}
{type_rules_text}
{len(type_rules) + 4}. 只输出一个 JSON 对象，不要 markdown，不要解释。

字段说明：
{field_lines}

输出 JSON 的 key 必须且仅能包含：{keys}"""


def build_user_prompt(
    ocr_text: str,
    *,
    personnel: str | None = None,
    attachment_name: str | None = None,
) -> str:
    prompt = f"OCR 文本如下：\n\n{ocr_text.strip()}"
    if attachment_name:
        prompt += f"\n\n业务侧声明的附件名称：{attachment_name.strip()}"
    if personnel:
        prompt += f"\n\n人员标识 personnel（原样保留，不要修改）：{personnel}"
    return prompt


def build_balance_sheet_total_assets_system_prompt() -> str:
    return """你是审计报告资产负债表解析助手。
任务：从 OCR 识别的资产负债表页面文本中，提取 totalAssets（资产总额）。

严格要求：
1. 只提取 OCR 文本中明确出现的金额，禁止猜测、补全或编造。
2. 仅取「资产总计」或「资产总额」行（不是流动资产合计、非流动资产合计）的金额。
3. 若表格分列「合并」「公司」，取「期末余额」（或「上年年末余额」对应列中的期末侧）下「合并」列的金额。
4. 若无「合并/公司」分列，取「期末余额」侧第一个金额。
5. 单位统一为人民币元，输出纯数字字符串，不含逗号和单位；原文为万元需换算为元。
6. 找不到则 totalAssets 输出空字符串 ""。
7. 只输出一个 JSON 对象，不要 markdown，不要解释。

输出 JSON 格式：{"totalAssets": "..."}"""


def build_balance_sheet_total_assets_user_prompt(balance_sheet_text: str) -> str:
    return f"以下为资产负债表页面的 OCR 文本，请提取 totalAssets：\n\n{balance_sheet_text.strip()}"


AUDIT_COVER_FIELD_KEYS = ("companyName", "accountingFirmName", "reportCode")


def build_audit_cover_system_prompt() -> str:
    field_lines = "\n".join(
        f'- "{key}": {DOCUMENT_FIELD_SCHEMAS[3][key]}'
        for key in AUDIT_COVER_FIELD_KEYS
    )
    keys = ", ".join(f'"{key}"' for key in AUDIT_COVER_FIELD_KEYS)
    return f"""你是审计报告封面解析助手。
任务：从 OCR 识别的审计报告首页/封面文本中，提取指定字段并输出 JSON。

严格要求：
1. 只提取 OCR 文本中明确出现的信息，禁止猜测、补全或编造。
2. 找不到的字段必须输出空字符串 ""，不要输出 null。
3. companyName 取被审计单位/客户名称（售电公司），通常是带「有限公司/股份有限公司」的企业全称；不要取会计师事务所名称。
4. accountingFirmName 必须是出具报告的会计师事务所全称（如「致同会计师事务所(特殊普通合伙)」）。
   - 必须包含「会计师事务所」或「审计事务所」。
   - 禁止输出二维码说明、查验提示、监管平台链接等说明文字（如「此码用于证明…」「执业许可」「扫一扫」等）。
5. reportCode 优先取封面「报告编码」（如「京25CLW5B6TX」）；若无报告编码，再取审计报告文号/审字号。
6. 只输出一个 JSON 对象，不要 markdown，不要解释。

字段说明：
{field_lines}

输出 JSON 的 key 必须且仅能包含：{keys}"""


def build_audit_cover_user_prompt(cover_text: str) -> str:
    return f"以下为审计报告首页 OCR 文本，请提取封面字段：\n\n{cover_text.strip()}"


CAPITAL_VERIFICATION_COVER_FIELD_KEYS = ("companyName", "accountingFirmName", "reportCode")


def build_capital_verification_cover_system_prompt() -> str:
    field_lines = "\n".join(
        f'- "{key}": {DOCUMENT_FIELD_SCHEMAS[4][key]}'
        for key in CAPITAL_VERIFICATION_COVER_FIELD_KEYS
    )
    keys = ", ".join(f'"{key}"' for key in CAPITAL_VERIFICATION_COVER_FIELD_KEYS)
    return f"""你是验资报告封面解析助手。
任务：从 OCR 识别的验资报告首页/封面文本中，提取指定字段并输出 JSON。

严格要求：
1. 只提取 OCR 文本中明确出现的信息，禁止猜测、补全或编造。
2. 找不到的字段必须输出空字符串 ""，不要输出 null。
3. companyName 取被验资单位/公司名称（售电公司），通常是带「有限公司/股份有限公司」的企业全称；不要取会计师事务所名称。
4. accountingFirmName 必须是出具验资报告的会计师事务所全称（如「立信会计师事务所(特殊普通合伙)」）。
   - 必须包含「会计师事务所」或「审计事务所」。
   - 禁止输出二维码说明、查验提示、监管平台链接等说明文字（如「此码用于证明…」「执业许可」「扫一扫」等）。
5. reportCode 优先取封面「报告编码」；若无报告编码，再取验资报告文号（如「京信验字(2023)第12345号」）。
6. 只输出一个 JSON 对象，不要 markdown，不要解释。

字段说明：
{field_lines}

输出 JSON 的 key 必须且仅能包含：{keys}"""


GRADE_PROTECTION_FIELD_KEYS = ("companyName", "systemLevel")
SOFTWARE_COPYRIGHT_FIELD_KEYS = ("copyrightOwner",)


def build_grade_protection_system_prompt() -> str:
    field_lines = "\n".join(
        f'- "{key}": {DOCUMENT_FIELD_SCHEMAS[6][key]}'
        for key in GRADE_PROTECTION_FIELD_KEYS
    )
    keys = ", ".join(f'"{key}"' for key in GRADE_PROTECTION_FIELD_KEYS)
    return f"""你是等级保护备案证明解析助手。
任务：从 OCR 识别的等保备案全文（可能含多页，以「--- 第 N 页 ---」分隔）中提取指定字段并输出 JSON。

严格要求：
1. 只提取 OCR 文本中明确出现的信息，禁止猜测、补全或编造。
2. 找不到的字段必须输出空字符串 ""，不要输出 null。
3. companyName 取备案单位/单位名称（售电公司企业全称），不要取公安机关名称。
4. systemLevel 取安全保护等级/定级等级，输出一级/二级/三级/四级/五级（如「第三级」「第3级」规范为「三级」）。
5. 信息可能在首页以外的页面，请通读全部 OCR 文本后再提取。
6. 只输出一个 JSON 对象，不要 markdown，不要解释。

字段说明：
{field_lines}

输出 JSON 的 key 必须且仅能包含：{keys}"""


def build_grade_protection_user_prompt(full_text: str) -> str:
    return f"以下为等级保护备案证明全文 OCR 文本，请提取字段：\n\n{full_text.strip()}"


def build_software_copyright_system_prompt() -> str:
    field_lines = "\n".join(
        f'- "{key}": {DOCUMENT_FIELD_SCHEMAS[6][key]}'
        for key in SOFTWARE_COPYRIGHT_FIELD_KEYS
    )
    keys = ", ".join(f'"{key}"' for key in SOFTWARE_COPYRIGHT_FIELD_KEYS)
    return f"""你是计算机软件著作权登记证书解析助手。
任务：从 OCR 识别的软著证书首页/封面文本中提取指定字段并输出 JSON。

严格要求：
1. 只提取 OCR 文本中明确出现的信息，禁止猜测、补全或编造。
2. 找不到的字段必须输出空字符串 ""，不要输出 null。
3. copyrightOwner 取著作权人/权利人（售电公司企业全称）。
4. 只输出一个 JSON 对象，不要 markdown，不要解释。

字段说明：
{field_lines}

输出 JSON 的 key 必须且仅能包含：{keys}"""


def build_software_copyright_user_prompt(cover_text: str) -> str:
    return f"以下为软件著作权登记证书首页 OCR 文本，请提取字段：\n\n{cover_text.strip()}"


def build_capital_verification_cover_user_prompt(cover_text: str) -> str:
    return f"以下为验资报告首页 OCR 文本，请提取封面字段：\n\n{cover_text.strip()}"


def build_business_license_seal_fields_system_prompt() -> str:
    return """你是营业执照公章区域视觉识别助手。
任务：仅从公章区域图片或 OCR 原文中识别 registerAuthority（登记机关）和 approvalDate（核准日期）。

背景说明：
- registerAuthority 指右下角红色圆形公章内环绕的机关名称（如「深圳市市场监督管理局」）。
- approvalDate 指该公章附近印刷的核准/发证日期，与成立日期不同，格式 YYYY-MM-DD。
- 「登记机关」「发照机关」只是印刷标题，不是 registerAuthority 的值。

识别规则：
1. 必须能从图片中直接看到红色公章内的机关名称，或 OCR 文本中明确出现该机关名称，才能输出 registerAuthority。
2. approvalDate 必须来自公章附近可见的日期，或 OCR 文本中明确出现的核准/发证日期。
3. 禁止根据住所、统一社会信用代码、城市、省份等信息推测、补全或编造。
4. 禁止将页脚监制单位（如「国家市场监督管理总局」）当作 registerAuthority。
5. 无法从图片或 OCR 明确辨认时，对应字段必须输出空字符串 ""。
6. 只输出一个 JSON 对象，不要 markdown，不要解释。

输出 JSON 格式：{"registerAuthority": "...", "approvalDate": "..."}"""


def build_business_license_seal_fields_user_prompt(
    page_text: str,
    seal_text: str,
    *,
    has_seal_image: bool = False,
) -> str:
    sections: list[str] = []
    if has_seal_image:
        sections.append(
            "附件为营业执照右下角公章区域图片。"
            "请仅根据图片中可见的公章文字与核准日期识别，禁止推测。"
        )
    if page_text.strip():
        sections.append(f"以下为营业执照全文 OCR（仅作对照，不可用于推测）：\n\n{page_text.strip()}")
    if seal_text.strip():
        sections.append(
            "以下为公章区域 OCR（若已有明确机关名称或日期可直接采用，否则留空）：\n\n"
            f"{seal_text.strip()}"
        )
    return "\n\n".join(sections)


def build_business_license_register_authority_system_prompt() -> str:
    return build_business_license_seal_fields_system_prompt()


def build_business_license_register_authority_user_prompt(
    page_text: str,
    seal_text: str,
    *,
    has_seal_image: bool = False,
) -> str:
    return build_business_license_seal_fields_user_prompt(
        page_text,
        seal_text,
        has_seal_image=has_seal_image,
    )
