from __future__ import annotations


def is_platform_success_code(code: object) -> bool:
    if code in {0, "0", 0.0}:
        return True
    if isinstance(code, str) and code.strip() == "0":
        return True
    return False
