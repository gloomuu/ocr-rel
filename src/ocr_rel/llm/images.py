from __future__ import annotations

import base64
import io

from PIL import Image


def image_to_data_url(image: Image.Image, *, image_format: str = "JPEG") -> str:
    converted = image.convert("RGB") if image.mode not in {"RGB", "L"} else image
    buffer = io.BytesIO()
    converted.save(buffer, format=image_format, quality=90)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/{image_format.lower()};base64,{encoded}"
