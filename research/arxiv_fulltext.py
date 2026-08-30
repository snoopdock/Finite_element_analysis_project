#!/usr/bin/env python3
"""
arXiv Full-Text Retriever with OCR Support
Downloads PDFs, extracts text with PyMuPDF, runs OCR if scanned.
"""

import re
import sys
import time
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import List, Dict

from utils.text import clean_text
from research.content_cache import read_cache, write_cache, get_cache_path
from research.ocr_engine import ocr_pdf_bytes, should_run_ocr, is_tesseract_available

USER_AGENT = (
    "FEA_Pipeline_Bot/1.0 "
    "(https://github.com/snoopdock/Finite_element_analysis_project; "
    "mailto:bot@example.com)"
)


def _extract_text_from_pdf_bytes(pdf_bytes: bytes) -> tuple:
    """
    Extract text from PDF bytes.
    Returns (text, page_count, needs_ocr).
    """
    text_pages = []
    page_count = 0
    try:
        import pymupdf
        with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
            page_count = len(doc)
            for page in doc:
                text_pages.append(page.get_text())
    except Exception as e:
        print(f"  [arXiv] PDF parse error: {e}", file=sys.stderr)
        return "", 0, True

    full_text = "\n".join(text_pages)
    needs_ocr = should_run_ocr(full_text, page_count)

    return full_text, page_count, needs_ocr


def search_arxiv(query: str, max_results: int = 3) -> List[Dict]:
    """Search arXiv, download PDFs, extract text (with OCR fallback)."""
    url = "https://export.arxiv.org/api/query"
    params = {
        "search_query": f"all:{query}",
        "start": 0,
        "max_results": max_results,
        "sortBy": "relevance",
    }

    req = urllib.request.Request(
        url + "?" + urllib.parse.urlencode(params),
        headers={"User-Agent": USER_AGENT}
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            xml_data = response.read()
    except Exception as e:
        print(f"  [arXiv] API error: {e}", file=sys.stderr)
        return []

    root = ET.fromstring(xml_data)
    ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
    sources = []

    for entry in root.findall("atom:entry", ns):
        try:
            id_text = entry.find("atom:id", ns).text.strip()
            uid = id_text.split("/abs/")[-1]
            source_id = "arxiv_" + re.sub(r"[^a-zA-Z0-9_\.]+", "_", uid)

            title = clean_text(entry.find("atom:title", ns).text, 300)
            summary = clean_text(entry.find("atom:summary", ns).text, 2000)
            authors = [a.find("atom:name", ns).text for a in entry.findall("atom:author", ns)]
            published = entry.find("atom:published", ns).text

            pdf_url = f"https://arxiv.org/pdf/{uid}.pdf"

            # Check cache first
            cached_text = read_cache(source_id)
            if cached_text:
                status = "cached_full_text"
                full_text = cached_text
            else:
                status = "metadata_only"
                full_text = ""
                try:
                    req_pdf = urllib.request.Request(pdf_url, headers={"User-Agent": USER_AGENT})
                    with urllib.request.urlopen(req_pdf, timeout=60) as response_pdf:
                        pdf_bytes = response_pdf.read()

                    extracted_text, page_count, needs_ocr = _extract_text_from_pdf_bytes(pdf_bytes)

                    if needs_ocr:
                        print(f"  [arXiv] Scanned PDF detected, running OCR: {uid}", file=sys.stderr)
                        
                        if is_tesseract_available():
                            ocr_text, _, _ = ocr_pdf_bytes(pdf_bytes, dpi=300)
                            
                            if ocr_text and len(ocr_text.split()) > 50:
                                full_text = ocr_text
                                write_cache(source_id, full_text)
                                status = "ocr_full_text"
                            else:
                                status = "ocr_failed"
                        else:
                            status = "ocr_unavailable"
                            print(f"  [arXiv] Tesseract not installed, skipping OCR", file=sys.stderr)
                    else:
                        if extracted_text and len(extracted_text.split()) > 50:
                            full_text = extracted_text
                            write_cache(source_id, full_text)
                            status = "parsed_full_text"
                        else:
                            status = "scanned_or_empty"

                    time.sleep(3)

                except Exception as e:
                    print(f"  [arXiv] Download failed for {uid}: {e}", file=sys.stderr)

            sources.append({
                "source_id": source_id,
                "url": pdf_url,
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "retriever_module": "research.arxiv_fulltext",
                "content_type": "application/pdf",
                "title": title,
                "authors": authors,
                "metadata": {
                    "abstract": summary,
                    "published": published,
                    "word_count": len(full_text.split()) if full_text else len(summary.split()),
                },
                "full_text_path": str(get_cache_path(source_id)) if full_text else None,
                "status": status,
            })

        except Exception as e:
            print(f"  [arXiv] Error processing entry: {e}", file=sys.stderr)
            continue

    return sources
