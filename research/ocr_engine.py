#!/usr/bin/env python3
"""
OCR Engine for Scanned PDFs
Uses Tesseract OCR with PyMuPDF for page rendering.
Designed to run in GitHub Actions (lightweight, fast).
"""

import sys
import io
from pathlib import Path
from typing import Optional

try:
    import pymupdf  # PyMuPDF
    import pytesseract
    from PIL import Image
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False


def is_tesseract_available() -> bool:
    """Check if Tesseract OCR is installed and accessible."""
    if not TESSERACT_AVAILABLE:
        return False
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def ocr_pdf_bytes(pdf_bytes: bytes, dpi: int = 300, lang: str = "eng") -> tuple:
    """
    Run OCR on a scanned PDF.
    
    Args:
        pdf_bytes: Raw PDF file bytes
        dpi: Resolution for rendering (300 is good balance of speed/quality)
        lang: Tesseract language code (eng, deu, fra, etc.)
        
    Returns:
        tuple: (extracted_text, page_count, is_scanned)
    """
    if not is_tesseract_available():
        print("  [OCR] Tesseract not available. Install with: apt-get install tesseract-ocr", file=sys.stderr)
        return "", 0, False

    text_pages = []
    page_count = 0

    try:
        with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
            page_count = len(doc)
            print(f"  [OCR] Processing {page_count} pages...", file=sys.stderr)

            for i, page in enumerate(doc):
                # Render page to image at specified DPI
                # zoom factor = dpi / 72 (PDF default is 72 DPI)
                zoom = dpi / 72
                mat = pymupdf.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=mat)

                # Convert to PIL Image
                img_data = pix.tobytes("png")
                img = Image.open(io.BytesIO(img_data))

                # Run Tesseract OCR
                page_text = pytesseract.image_to_string(img, lang=lang)
                text_pages.append(page_text)

                # Progress indicator for long documents
                if (i + 1) % 10 == 0:
                    print(f"  [OCR] Processed {i + 1}/{page_count} pages", file=sys.stderr)

    except Exception as e:
        print(f"  [OCR] Error during OCR: {e}", file=sys.stderr)
        return "", page_count, False

    full_text = "\n".join(text_pages)
    return full_text, page_count, True


def ocr_pdf_file(pdf_path: Path, dpi: int = 300, lang: str = "eng") -> tuple:
    """Run OCR on a PDF file path."""
    try:
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()
        return ocr_pdf_bytes(pdf_bytes, dpi, lang)
    except Exception as e:
        print(f"  [OCR] Error reading {pdf_path}: {e}", file=sys.stderr)
        return "", 0, False


def should_run_ocr(text: str, page_count: int, threshold_words_per_page: int = 10) -> bool:
    """
    Determine if OCR should be run based on text extraction quality.
    
    Returns True if the document appears to be scanned (low text per page).
    """
    if not text or not text.strip():
        return True
    
    words = text.split()
    words_per_page = len(words) / max(page_count, 1)
    
    return words_per_page < threshold_words_per_page
