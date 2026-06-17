from io import BytesIO

import fitz
from PIL import Image

from ocr_rel.config import settings

IMAGE_SUPPORTED_TYPES = {1, 2}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}
PDF_EXTENSIONS = {".pdf"}


def is_pdf(content: bytes) -> bool:
    return content.startswith(b"%PDF")


def is_image(content: bytes) -> bool:
    return content.startswith(b"\x89PNG") or content.startswith(b"\xff\xd8\xff")


def _extension(filename: str | None) -> str:
    if not filename:
        return ""
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def detect_document_kind(content: bytes, filename: str | None = None) -> str:
    if is_pdf(content):
        return "pdf"
    if is_image(content):
        return "image"

    ext = _extension(filename)
    if ext == "pdf":
        return "pdf"
    if f".{ext}" in IMAGE_EXTENSIONS:
        return "image"
    return "unknown"


def detect_file_format_label(content: bytes, filename: str | None = None) -> str | None:
    kind = detect_document_kind(content, filename)
    if kind == "pdf":
        return "PDF"
    if kind == "image":
        ext = _extension(filename)
        mapping = {"png": "PNG", "jpg": "JPG", "jpeg": "JPG"}
        return mapping.get(ext, "IMAGE")
    ext = _extension(filename)
    if ext:
        return ext.upper()
    return None


def pdf_to_images(pdf_bytes: bytes, dpi: int | None = None) -> list[Image.Image]:
    """Convert each PDF page to a PIL Image."""
    render_dpi = dpi or settings.pdf_render_dpi
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    images: list[Image.Image] = []
    try:
        zoom = render_dpi / 72.0
        matrix = fitz.Matrix(zoom, zoom)
        for page in doc:
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)
            image = Image.open(BytesIO(pixmap.tobytes("png")))
            images.append(image.convert("RGB"))
    finally:
        doc.close()
    return images


def image_bytes_to_images(content: bytes) -> list[Image.Image]:
    image = Image.open(BytesIO(content))
    return [image.convert("RGB")]


def document_to_images(
    content: bytes,
    *,
    doc_type: int,
    filename: str | None = None,
) -> list[Image.Image]:
    kind = detect_document_kind(content, filename)

    if kind == "pdf":
        images = pdf_to_images(content)
        if not images:
            raise ValueError("PDF contains no pages")
        return images

    if kind == "image":
        if doc_type not in IMAGE_SUPPORTED_TYPES:
            raise ValueError(
                f"Image files are only supported for document types {sorted(IMAGE_SUPPORTED_TYPES)}"
            )
        return image_bytes_to_images(content)

    if doc_type in IMAGE_SUPPORTED_TYPES:
        raise ValueError("Unsupported file format; expected PDF or image (png, jpg, jpeg)")
    raise ValueError("Only PDF files are supported for this document type")
