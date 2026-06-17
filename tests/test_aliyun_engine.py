from io import BytesIO

from PIL import Image

from ocr_rel.ocr.aliyun_engine import parse_recognize_general_response, prepare_image_bytes


def _make_image(size: tuple[int, int] = (800, 600)) -> Image.Image:
    return Image.new("RGB", size, color=(255, 255, 255))


def test_prepare_image_bytes_returns_jpeg_binary() -> None:
    buffer = prepare_image_bytes(_make_image())
    data = buffer.getvalue()
    assert data.startswith(b"\xff\xd8\xff")


def test_prepare_image_bytes_from_rgba() -> None:
    image = Image.new("RGBA", (100, 100), color=(255, 0, 0, 128))
    buffer = prepare_image_bytes(image)
    assert buffer.getvalue().startswith(b"\xff\xd8\xff")


def test_prepare_image_bytes_resizes_large_image() -> None:
    buffer = prepare_image_bytes(_make_image((9000, 6000)))
    image = Image.open(BytesIO(buffer.getvalue()))
    assert max(image.size) <= 4096


def test_parse_recognize_general_response() -> None:
    payload = '{"content":"hello world","prism_version":"1.0"}'
    assert parse_recognize_general_response(payload) == "hello world"
    assert parse_recognize_general_response(None) == ""
    assert parse_recognize_general_response("plain-text") == "plain-text"
