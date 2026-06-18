from ocr_rel.parsers.type1_business_license import BusinessLicenseParser
from ocr_rel.parsers.type2_legal_person_id import LegalPersonIdParser


def test_business_license_parser() -> None:
    text = """
    营业执照
    名称：河南省泛物网络科技有限公司
    统一社会信用代码：91410000MA9ABCDEF0
    住所：河南省郑州市金水区某某路 100 号
    成立日期：2020年05月18日
    登记机关：郑州市市场监督管理局
    核准日期：2023年01月10日
    """
    result = BusinessLicenseParser().parse(text)
    assert result["companyName"] == "河南省泛物网络科技有限公司"
    assert result["unifiedSocialCreditCode"] == "91410000MA9ABCDEF0"
    assert result["establishDate"] == "2020-05-18"
    assert result["approvalDate"] == "2023-01-10"
    assert "郑州" in result["registeredAddress"]
    assert "市场监督管理局" in result["registerAuthority"]


def test_business_license_parser_multiline_labels() -> None:
    text = """
    统一社会信用代码
    91440300682024797J
    名 称
    深圳市广田集团股份有限公司
    住 所
    深圳市罗湖区笋岗街道田心社区红岭北路2188号广田大厦27层
    成立日期
    2008年11月04日
    登记机关
    深圳市市场监督管理局
    核准日期
    2021年06月15日
    1.商事主体的经营范围由章程确定。
    2.商事主体经营范围和许可审批项目等有关企业
    """
    result = BusinessLicenseParser().parse(text)
    assert result["unifiedSocialCreditCode"] == "91440300682024797J"
    assert result["companyName"] == "深圳市广田集团股份有限公司"
    assert result["establishDate"] == "2008-11-04"
    assert result["approvalDate"] == "2021-06-15"
    assert result["registeredAddress"] == "深圳市罗湖区笋岗街道田心社区红岭北路2188号广田大厦27层"
    assert result["registerAuthority"] == "深圳市市场监督管理局"
    assert "经营范围" not in result["registeredAddress"]
    assert "年度报告" not in result["registerAuthority"]


def test_business_license_parser_inline_with_noise() -> None:
    text = """
    统一社会信用代码91440300682024797J
    名称深圳测试售电有限公司
    住所深圳市罗湖区笋岗街道田心社区红岭北路2188号广田大厦27层 重 1.商事主体的经营范围由章程确定。
    成立日期2008-11-04
    登记机关深圳市市场监督管理局
    """
    result = BusinessLicenseParser().parse(text)
    assert result["companyName"] == "深圳测试售电有限公司"
    assert result["registeredAddress"].startswith("深圳市罗湖区")
    assert "商事主体" not in result["registeredAddress"]
    assert result["registerAuthority"] == "深圳市市场监督管理局"


def test_business_license_parser_yichuang_case() -> None:
    text = """
    营业执照
    统一社会信用代码
    91440300682024797J
    名称
    深圳壹创国际设计股份有限公司
    类型
    股份有限公司
    法定代表人
    严定
    经营范围
    建筑工程设计
    注册资本
    8100.000000万元
    成立日期
    2008年11月04日
    营业期限
    2008年11月04日至长期
    住所
    深圳市罗湖区笋岗街道田心社区红岭北路2188号广田大厦27层
    登记机关
    深圳市市场监督管理局
    2020年05月20日
    1.应向商事登记机关申请，提交上一自然年度的年度报告。
    """
    result = BusinessLicenseParser().parse(text)
    assert result["companyName"] == "深圳壹创国际设计股份有限公司"
    assert result["registeredAddress"] == "深圳市罗湖区笋岗街道田心社区红岭北路2188号广田大厦27层"
    assert result["registerAuthority"] == "深圳市市场监督管理局"
    assert result["approvalDate"] == "2020-05-20"
    assert result["establishDate"] == "2008-11-04"


def test_business_license_parser_bottom_right_date_without_label() -> None:
    text = """
    91440300682024797J
    深圳壹创国际设计股份有限公司
    成立日期2008年11月04日
    住所深圳市南山区粤海街道科技南十二路6号中检大厦1801
    深圳市市场监督管理局 2019年03月12日
    应向商事登记机关申请
    """
    result = BusinessLicenseParser().parse(text)
    assert result["registeredAddress"] == "深圳市南山区粤海街道科技南十二路6号中检大厦1801"
    assert result["registerAuthority"] == "深圳市市场监督管理局"
    assert result["approvalDate"] == "2019-03-12"
    assert result["registerAuthority"] != "向商事"


def test_legal_person_id_parser() -> None:
    text = """
    姓名 张三
    性别 男
    公民身份号码 410105199001011234
    """
    result = LegalPersonIdParser().parse(text)
    assert result["name"] == "张三"
    assert result["idCardNumber"] == "410105199001011234"


def test_audit_report_parser_cover_only() -> None:
    from ocr_rel.parsers.type3_audit_report import AuditReportParser

    text = """
    审计报告
    被审计单位：河南测试售电有限公司
    会计师事务所：立信会计师事务所（特殊普通合伙）河南分所
    报告文号：信会师报字[2023]第ZA12345号
    我们审计了河南测试售电有限公司财务报表
    """
    result = AuditReportParser().parse(text)
    assert result["companyName"] == "河南测试售电有限公司"
    assert "立信会计师事务所" in result["accountingFirmName"]
    assert result["reportCode"] == "信会师报字[2023]第ZA12345号"
    assert result["totalAssets"] == ""


def test_audit_report_parser_report_encoding_code() -> None:
    from ocr_rel.parsers.type3_audit_report import AuditReportParser

    text = """
    深圳壹创国际设计股份有限公司
    二〇二四年度
    审计报告
    致同会计师事务所 (特殊普通合伙)
    此码用于证明该审计报告是否由具有执业许可的会计师事务所出具
    报告编码：京25CLW5B6TX
    """
    result = AuditReportParser().parse(text)
    assert result["companyName"] == "深圳壹创国际设计股份有限公司"
    assert result["reportCode"] == "京25CLW5B6TX"


def test_audit_report_parser_balance_sheet_page() -> None:
    from ocr_rel.parsers.type3_audit_report import AuditReportParser

    text = """
    资产负债表
    期末余额 期初余额
    资产总计 21,000,000.00 18,000,000.00
    """
    result = AuditReportParser().parse(text)
    assert result["totalAssets"] == "21000000"


def test_capital_verification_parser_cover() -> None:
    from ocr_rel.parsers.type4_capital_verification import CapitalVerificationParser

    text = """
    验资报告
    被验资单位：河南测试售电有限公司
    会计师事务所：立信会计师事务所（特殊普通合伙）河南分所
    验资报告文号：京信验字(2023)第12345号
    """
    result = CapitalVerificationParser().parse(text)
    assert result["companyName"] == "河南测试售电有限公司"
    assert "立信会计师事务所" in result["accountingFirmName"]
    assert result["reportCode"] == "京信验字(2023)第12345号"
