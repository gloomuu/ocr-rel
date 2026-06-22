from ocr_rel.parsers.base import BaseParser
from ocr_rel.parsers.type1_business_license import BusinessLicenseParser
from ocr_rel.parsers.type2_legal_person_id import LegalPersonIdParser
from ocr_rel.parsers.type3_audit_report import AuditReportParser
from ocr_rel.parsers.type4_capital_verification import CapitalVerificationParser
from ocr_rel.parsers.type5_employee_id import EmployeeIdParser
from ocr_rel.parsers.type6_grade_protection import TechSupportDocParser
from ocr_rel.parsers.type7_credit_report import CreditReportParser
from ocr_rel.parsers.type8_credit_proof import CreditProofParser

_credit_proof_parser = CreditProofParser()

PARSER_REGISTRY: dict[int, BaseParser] = {
    1: BusinessLicenseParser(),
    2: LegalPersonIdParser(),
    3: AuditReportParser(),
    4: CapitalVerificationParser(),
    5: EmployeeIdParser(),
    6: TechSupportDocParser(),
    7: CreditReportParser(),
    8: _credit_proof_parser,
    9: _credit_proof_parser,
    10: _credit_proof_parser,
    11: _credit_proof_parser,
}


def get_parser(doc_type: int) -> BaseParser:
    parser = PARSER_REGISTRY.get(doc_type)
    if parser is None:
        raise ValueError(f"Parser for document type {doc_type} is not implemented yet")
    return parser


def supported_types() -> list[int]:
    return sorted(PARSER_REGISTRY.keys())
