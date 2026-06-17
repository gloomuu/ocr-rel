from PIL import Image

from ocr_rel.ocr.seal_region import crop_business_license_seal_region


def test_crop_business_license_seal_region() -> None:
    image = Image.new("RGB", (1000, 1400), color=(255, 255, 255))
    cropped = crop_business_license_seal_region(image)
    assert cropped.size == (480, 630)
