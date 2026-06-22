from io import BytesIO

import fitz
from PIL import Image

from ocr_rel.config import settings
from ocr_rel.logging_config import get_logger, log_step

logger = get_logger(__name__)

IMAGE_SUPPORTED_TYPES = {1, 2, 5, 7, 8, 9, 10, 11}
COVER_PAGE_ONLY_TYPES = {4, 7, 8, 9, 10, 11}
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


def pdf_to_images(
    pdf_bytes: bytes,
    dpi: int | None = None,
    *,
    max_pages: int | None = None,
) -> list[Image.Image]:
    """Convert PDF pages to PIL Images; optionally limit to the first N pages."""
    render_dpi = dpi or settings.pdf_render_dpi
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    images: list[Image.Image] = []
    try:
        zoom = render_dpi / 72.0
        matrix = fitz.Matrix(zoom, zoom)
        total_pages = len(doc)
        page_count = total_pages if max_pages is None else min(total_pages, max_pages)
        for page_index in range(page_count):
            pixmap = doc[page_index].get_pixmap(matrix=matrix, alpha=False)
            image = Image.open(BytesIO(pixmap.tobytes("png")))
            images.append(image.convert("RGB"))
        if max_pages is not None:
            skipped_pages = max(0, total_pages - page_count)
            log_step(
                logger,
                step="pdf.render.limited",
                message="PDF 按页数上限渲染",
                totalPagesInPdf=total_pages,
                renderedPages=page_count,
                maxPages=max_pages,
                skippedPages=skipped_pages,
            )
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
    max_pages: int | None = None,
) -> list[Image.Image]:
    kind = detect_document_kind(content, filename)
    page_limit = max_pages
    if page_limit is None and doc_type in COVER_PAGE_ONLY_TYPES:
        page_limit = 1

    if kind == "pdf":
        if doc_type in COVER_PAGE_ONLY_TYPES:
            log_step(
                logger,
                step="pdf.cover_only",
                message=f"type{doc_type} 启用仅首页模式（maxPages=1）",
                docType=doc_type,
                maxPages=page_limit,
            )
        images = pdf_to_images(content, max_pages=page_limit)
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
