from __future__ import annotations

# Substrings that indicate a model likely supports image input (OpenAI-compatible APIs).
_VISION_MODEL_MARKERS = (
    "vl",
    "vision",
    "gpt-4o",
    "4o-mini",
    "gemini",
    "ui-tars",
    "qvq",
)


def model_supports_vision(model_name: str) -> bool:
    normalized = model_name.strip().lower()
    if not normalized:
        return False
    return any(marker in normalized for marker in _VISION_MODEL_MARKERS)
