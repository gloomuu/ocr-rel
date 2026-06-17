from ocr_rel.parsers.base import BaseParser
from ocr_rel.parsers.type1_business_license import BusinessLicenseParser
from ocr_rel.parsers.type2_legal_person_id import LegalPersonIdParser
from ocr_rel.parsers.type3_audit_report import AuditReportParser

PARSER_REGISTRY: dict[int, BaseParser] = {
    1: BusinessLicenseParser(),
    2: LegalPersonIdParser(),
    3: AuditReportParser(),
}


def get_parser(doc_type: int) -> BaseParser:
    parser = PARSER_REGISTRY.get(doc_type)
    if parser is None:
        raise ValueError(f"Parser for document type {doc_type} is not implemented yet")
    return parser


def supported_types() -> list[int]:
    return sorted(PARSER_REGISTRY.keys())
