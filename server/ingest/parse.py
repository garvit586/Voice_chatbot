"""Document parsing: PDF → list of (page_no, text, figure_bytes | None)."""

from __future__ import annotations

from dataclasses import dataclass

import fitz  # PyMuPDF


@dataclass
class ParsedPage:
    page: int
    text: str
    figure: bytes | None  # JPEG bytes of the page image, if significant


def parse_pdf(data: bytes, dpi: int = 72) -> list[ParsedPage]:
    doc = fitz.open(stream=data, filetype="pdf")
    pages: list[ParsedPage] = []
    for i, page in enumerate(doc):
        text = page.get_text("text").strip()
        if not text:
            continue
        # Render a small JPEG of pages that have significant figures
        fig: bytes | None = None
        blocks = page.get_text("blocks")
        has_images = any(b[6] == 1 for b in blocks)  # block type 1 = image
        if has_images:
            mat = fitz.Matrix(dpi / 72, dpi / 72)
            pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
            fig = pix.tobytes("jpeg")
        pages.append(ParsedPage(page=i + 1, text=text, figure=fig))
    return pages


def parse_text(data: bytes, mime: str) -> list[ParsedPage]:
    """Plain text or Markdown — one big 'page'."""
    text = data.decode("utf-8", errors="replace").strip()
    return [ParsedPage(page=1, text=text, figure=None)] if text else []


def parse(data: bytes, mime: str) -> list[ParsedPage]:
    if "pdf" in mime:
        return parse_pdf(data)
    return parse_text(data, mime)
