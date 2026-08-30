#!/usr/bin/env python3
"""
Semantic Scholar Retriever with OCR Support
Uses the free Semantic Scholar API to find papers and Open Access PDFs.
Runs OCR on scanned PDFs.
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

API_URL = "https://api.semanticscholar.org/graph/v1/paper/search"


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
        print(f"  [S2] PDF parse error: {e}", file=sys.stderr)
        return "", 0, True

    full_text = "\n".join(text_pages)
    needs_ocr = should_run_ocr(full_text, page_count)

    return full_text, page_count, needs_ocr


def search_semantic_scholar(query: str, max_results: int = 3) -> List[Dict]:
    """Search Semantic Scholar and download Open Access PDFs (with OCR)."""
    params = {
        "query": query,
        "limit": max_results,
        "fields": "title,abstract,authors,openAccessPdf,externalIds,year,citationCount"
    }
    headers = {"User-Agent": USER_AGENT}

    try:
        resp = requests.get(API_URL, params=params, headers=headers, timeout=30)
        if resp.status_code != 200:
            print(f"  [S2] API error: {resp.status_code}", file=sys.stderr)
            return []
        data = resp.json()
    except Exception as e:
        print(f"  [S2] Request error: {e}", file=sys.stderr)
        return []

    sources = []
    for paper in data.get("data", []):
        try:
            paper_id = paper.get("paperId", "")
            source_id = "s2_" + paper_id[:20]

            title = clean_text(paper.get("title", ""), 300)
            summary = clean_text(paper.get("abstract", "") or "", 2000)
            authors = [a.get("name", "") for a in paper.get("authors", []) if a.get("name")]
            year = paper.get("year")
            citation_count = paper.get("citationCount", 0)

            pdf_url = None
            open_access = paper.get("openAccessPdf")
            if open_access and open_access.get("url"):
                pdf_url = open_access["url"]

            # Check cache first
            cached_text = read_cache(source_id)
            if cached_text:
                full_text = cached_text
                status = "cached_full_text"
            elif pdf_url:
                full_text = ""
                status = "metadata_only"
                try:
                    req = urllib.request.Request(pdf_url, headers={"User-Agent": USER_AGENT})
                    with urllib.request.urlopen(req, timeout=60) as response:
                        pdf_bytes = response.read()

                    extracted_text, page_count, needs_ocr = _extract_text_from_pdf_bytes(pdf_bytes)

                    if needs_ocr:
                        print(f"  [S2] Scanned PDF detected, running OCR: {source_id}", file=sys.stderr)
                        
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
                    else:
                        if extracted_text and len(extracted_text.split()) > 50:
                            full_text = extracted_text
                            write_cache(source_id, full_text)
                            status = "parsed_full_text"
                        else:
                            status = "scanned_or_empty"

                except Exception as e:
                    print(f"  [S2] PDF download failed for {source_id}: {e}", file=sys.stderr)
            else:
                full_text = summary
                status = "abstract_only"

            sources.append({
                "source_id": source_id,
                "url": pdf_url or f"https://www.semanticscholar.org/paper/{paper_id}",
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "retriever_module": "research.semantic_scholar",
                "content_type": "application/pdf" if pdf_url else "text/plain",
                "title": title,
                "authors": authors,
                "metadata": {
                    "abstract": summary,
                    "year": year,
                    "citation_count": citation_count,
                    "word_count": len(full_text.split()) if full_text else len(summary.split()),
                },
                "full_text_path": str(get_cache_path(source_id)) if full_text else None,
                "status": status,
            })

            time.sleep(1)

        except Exception as e:
            print(f"  [S2] Error processing paper: {e}", file=sys.stderr)
            continue

    return sources
