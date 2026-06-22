from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from ocr_rel.models.schemas import CallbackPayload


def _total_assets_to_number(value: Any) -> float | int:
    if isinstance(value, bool):
        raise ValueError("invalid totalAssets")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value

    text = str(value).strip().replace(",", "")
    if not text:
        raise ValueError("empty totalAssets")

    try:
        amount = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"invalid totalAssets: {value}") from exc

    if amount == amount.to_integral_value():
        return int(amount)
    return float(amount)


def serialize_callback_detail(detail: dict[str, Any]) -> dict[str, Any]:
    serialized = dict(detail)
    if "totalAssets" in serialized:
        raw = serialized["totalAssets"]
        if raw in (None, ""):
            serialized.pop("totalAssets", None)
        else:
            serialized["totalAssets"] = _total_assets_to_number(raw)
    return serialized


def serialize_callback_payload(payload: CallbackPayload) -> dict[str, Any]:
    body = payload.model_dump()
    results = body.get("results") or []
    for result in results:
        result["detail"] = [
            serialize_callback_detail(item) for item in result.get("detail") or []
        ]
    return body
