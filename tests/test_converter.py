from io import BytesIO

import fitz
from PIL import Image

from ocr_rel.pdf.converter import detect_document_kind, detect_file_format_label, document_to_images, is_image, is_pdf


def _make_pdf_bytes() -> bytes:
    doc = fitz.open()
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


def test_document_to_images_png_for_type1() -> None:
    images = document_to_images(_make_png_bytes(), doc_type=1, filename="license.png")
    assert len(images) == 1
    assert images[0].size == (32, 32)


def test_document_to_images_png_for_type2() -> None:
    images = document_to_images(_make_png_bytes(), doc_type=2, filename="idcard.jpg")
    assert len(images) == 1


def test_detect_file_format_label() -> None:
    assert detect_file_format_label(_make_pdf_bytes(), "demo.pdf") == "PDF"
    assert detect_file_format_label(_make_png_bytes(), "demo.png") == "PNG"


def test_is_helpers() -> None:
    assert is_pdf(_make_pdf_bytes())
    assert is_image(_make_png_bytes())
