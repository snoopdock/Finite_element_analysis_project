#!/usr/bin/env python3
"""
Archive.org Retriever with OCR Support
Handles scanned PDFs by running Tesseract OCR when text extraction fails.
"""

import re
import sys
import time
import requests
import urllib.request
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
        print(f"  [Archive.org] PDF parse error: {e}", file=sys.stderr)
        return "", 0, True

    full_text = "\n".join(text_pages)
    needs_ocr = should_run_ocr(full_text, page_count)

    return full_text, page_count, needs_ocr


def search_archive_org(query: str, max_results: int = 2) -> List[Dict]:
    """
    Search Archive.org for books and papers.
    Uses OCR fallback for scanned PDFs.
    """
    url = "https://archive.org/advancedsearch.php"
    params = {
        "q": query,
        "fl[]": ["identifier", "title", "creator", "description", "year", "mediatype"],
        "sort[]": "downloads desc",
        "rows": max_results,
        "page": 1,
        "output": "json",
    }
    headers = {"User-Agent": USER_AGENT}

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=30)
        if resp.status_code != 200:
            return []
        data = resp.json()
    except Exception as e:
        print(f"  [Archive.org] Search error: {e}", file=sys.stderr)
        return []

    sources = []
    docs = data.get("response", {}).get("docs", [])

    for doc in docs:
        try:
            identifier = doc.get("identifier", "")
            mediatype = doc.get("mediatype", "")

            if mediatype not in ("texts", "books"):
                continue

            source_id = "ia_" + identifier
            title = clean_text(doc.get("title", ""), 300)

            summary = doc.get("description", "") or ""
            if isinstance(summary, list):
                summary = " ".join(summary)
            summary = clean_text(summary, 2000)

            authors = doc.get("creator", [])
            if isinstance(authors, str):
                authors = [authors]
            year = doc.get("year")

            # Check cache first
            cached_text = read_cache(source_id)
            if cached_text:
                full_text = cached_text
                status = "cached_full_text"
            else:
                full_text = ""
                status = "metadata_only"

                # Get file metadata
                meta_url = f"https://archive.org/metadata/{identifier}"
                try:
                    meta_resp = requests.get(meta_url, headers=headers, timeout=30)
                    if meta_resp.status_code != 200:
                        continue
                    metadata = meta_resp.json()
                except Exception:
                    continue

                # Look for pre-OCR'd text files (preferred) or PDFs
                txt_url = None
                pdf_url = None

                for f in metadata.get("files", []):
                    name = f.get("name", "")
                    if name.endswith("_djvu.txt") and not txt_url:
                        txt_url = f"https://archive.org/download/{identifier}/{name}"
                    elif name.endswith(".pdf") and not pdf_url:
                        pdf_url = f"https://archive.org/download/{identifier}/{name}"

                # Strategy 1: Try pre-OCR'd text (fastest)
                if txt_url:
                    try:
                        req = urllib.request.Request(txt_url, headers={"User-Agent": USER_AGENT})
                        with urllib.request.urlopen(req, timeout=60) as response:
                            full_text = response.read().decode("utf-8", errors="ignore")

                        if full_text and len(full_text.split()) > 100:
                            write_cache(source_id, full_text)
                            status = "parsed_full_text"
                    except Exception:
                        pass

                # Strategy 2: Try PDF extraction + OCR fallback
                elif pdf_url:
                    try:
                        req = urllib.request.Request(pdf_url, headers={"User-Agent": USER_AGENT})
                        with urllib.request.urlopen(req, timeout=60) as response:
                            pdf_bytes = response.read()

                        extracted_text, page_count, needs_ocr = _extract_text_from_pdf_bytes(pdf_bytes)

                        if needs_ocr:
                            print(f"  [Archive.org] Scanned PDF detected, running OCR: {identifier}", file=sys.stderr)
                            
                            if is_tesseract_available():
                                ocr_text, _, _ = ocr_pdf_bytes(pdf_bytes, dpi=300)
                                
                                if ocr_text and len(ocr_text.split()) > 100:
                                    full_text = ocr_text
                                    write_cache(source_id, full_text)
                                    status = "ocr_full_text"
                                    print(f"  [Archive.org] OCR successful: {len(ocr_text.split())} words", file=sys.stderr)
                                else:
                                    status = "ocr_failed"
                                    full_text = ""
                            else:
                                status = "ocr_unavailable"
                                full_text = ""
                                print(f"  [Archive.org] Tesseract not installed, skipping OCR", file=sys.stderr)
                        else:
                            if extracted_text and len(extracted_text.split()) > 100:
                                full_text = extracted_text
                                write_cache(source_id, full_text)
                                status = "parsed_full_text"

                    except Exception as e:
                        print(f"  [Archive.org] PDF error for {identifier}: {e}", file=sys.stderr)

            sources.append({
                "source_id": source_id,
                "url": f"https://archive.org/details/{identifier}",
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "retriever_module": "research.archive_org",
                "content_type": "application/pdf",
                "title": title,
                "authors": authors,
                "metadata": {
                    "abstract": summary,
                    "year": year,
                    "word_count": len(full_text.split()) if full_text else len(summary.split()),
                },
                "full_text_path": str(get_cache_path(source_id)) if full_text else None,
                "status": status,
            })

            time.sleep(1)

        except Exception as e:
            print(f"  [Archive.org] Error processing doc: {e}", file=sys.stderr)
            continue

    return sources
