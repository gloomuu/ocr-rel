from PIL import Image

from ocr_rel.llm.images import image_to_data_url


def test_image_to_data_url() -> None:
    image = Image.new("RGB", (10, 10), color=(255, 0, 0))
    data_url = image_to_data_url(image)
    assert data_url.startswith("data:image/jpeg;base64,")
