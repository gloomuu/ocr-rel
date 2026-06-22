from io import BytesIO

import fitz
from PIL import Image

from ocr_rel.pdf.converter import detect_document_kind, detect_file_format_label, document_to_images, is_image, is_pdf


def _make_pdf_bytes(*, pages: int = 1) -> bytes:
    doc = fitz.open()
    for _ in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), "sample")
    return doc.tobytes()


def _make_png_bytes() -> bytes:
    image = Image.new("RGB", (32, 32), color=(255, 255, 255))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_detect_document_kind() -> None:
    assert detect_document_kind(_make_pdf_bytes(), "demo.pdf") == "pdf"
    assert detect_document_kind(_make_png_bytes(), "demo.png") == "image"
    assert detect_document_kind(b"unknown", "demo.pdf") == "pdf"
    assert detect_document_kind(b"unknown", "demo.png") == "image"


def test_document_to_images_pdf() -> None:
    images = document_to_images(_make_pdf_bytes(), doc_type=1, filename="demo.pdf")
    assert len(images) == 1


def test_document_to_images_type4_uses_first_page_only() -> None:
    images = document_to_images(_make_pdf_bytes(pages=5), doc_type=4, filename="capital.pdf")
    assert len(images) == 1


def test_document_to_images_type7_uses_first_page_only() -> None:
    images = document_to_images(_make_pdf_bytes(pages=5), doc_type=7, filename="credit-report.pdf")
    assert len(images) == 1


def test_document_to_images_type8_uses_first_page_only() -> None:
    images = document_to_images(_make_pdf_bytes(pages=5), doc_type=8, filename="credit-proof.pdf")
    assert len(images) == 1


def test_document_to_images_png_for_type8() -> None:
    images = document_to_images(_make_png_bytes(), doc_type=8, filename="credit-proof.png")
    assert len(images) == 1


def test_document_to_images_type6_renders_all_pages() -> None:
    images = document_to_images(_make_pdf_bytes(pages=5), doc_type=6, filename="grade-protection.pdf")
    assert len(images) == 5


def test_document_to_images_png_for_type1() -> None:
    images = document_to_images(_make_png_bytes(), doc_type=1, filename="license.png")
    assert len(images) == 1
    assert images[0].size == (32, 32)


def test_document_to_images_png_for_type2() -> None:
    images = document_to_images(_make_png_bytes(), doc_type=2, filename="idcard.jpg")
    assert len(images) == 1


def test_document_to_images_png_for_type5() -> None:
    images = document_to_images(_make_png_bytes(), doc_type=5, filename="employee-id.jpg")
    assert len(images) == 1


def test_document_to_images_png_for_type7() -> None:
    images = document_to_images(_make_png_bytes(), doc_type=7, filename="credit-report.png")
    assert len(images) == 1


def test_detect_file_format_label() -> None:
    assert detect_file_format_label(_make_pdf_bytes(), "demo.pdf") == "PDF"
    assert detect_file_format_label(_make_png_bytes(), "demo.png") == "PNG"


def test_is_helpers() -> None:
    assert is_pdf(_make_pdf_bytes())
    assert is_image(_make_png_bytes())
