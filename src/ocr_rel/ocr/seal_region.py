from __future__ import annotations

from PIL import Image


def crop_business_license_seal_region(image: Image.Image) -> Image.Image:
    """Crop bottom-right region where the registration seal usually appears."""
    width, height = image.size
    left = int(width * 0.52)
    top = int(height * 0.55)
    return image.crop((left, top, width, height))
