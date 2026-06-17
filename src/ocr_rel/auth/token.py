from __future__ import annotations

import hashlib


def compute_auth_token(username: str, password: str, secret_key: str) -> str:
    raw = f"{username}{password}{secret_key}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def is_auth_configured(username: str, password: str, secret_key: str) -> bool:
    return bool(username and password and secret_key)
