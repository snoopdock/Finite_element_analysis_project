#!/usr/bin/env python3
"""
Semantic Scholar Retriever with OCR Support.

Uses the free Semantic Scholar API to find papers and, when an open-access PDF is
available, downloads it only in memory and caches the extracted full text in the
bounded local article cache. PDF binaries are never persisted by this module.
"""

from __future__ import annotations

import re
import sys
import time
import requests
import urllib.request
from datetime import datetime, timezone
from typing import Dict, List, Tuple

from utils.text import clean_text
from research.content_cache import get_cache_path, read_cache, write_cache
from research.ocr_engine import (
    is_tesseract_available,
    ocr_pdf_bytes,
    should_run_ocr,
)

USER_AGENT = (
    "FEA_Pipeline_Bot/1.0 "
    "(https://github.com/snoopdock/Finite_element_analysis_project; "
    "mailto:bot@example.com)"
)

API_URL = "https://api.semanticscholar.org/graph/v1/paper/search"


def _extract_text_from_pdf_bytes(pdf_bytes: bytes) -> Tuple[str, int, bool]:
    """Extract text from PDF bytes and report whether OCR is needed."""
    text_pages = []
    page_count = 0

    try:
        import pymupdf

        with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
            page_count = len(doc)
            for page in doc:
                text_pages.append(page.get_text())

    except Exception as exc:
        print(
            f"  [S2] PDF parse error: {exc}",
            file=sys.stderr,
        )
        return "", 0, True

    full_text = "\n".join(text_pages)
    return full_text, page_count, should_run_ocr(full_text, page_count)


def search_semantic_scholar(
    query: str,
    max_results: int = 3,
) -> List[Dict]:
    """Search Semantic Scholar and inspect Open Access full text when available."""
    params = {
        "query": query,
        "limit": max_results,
        "fields": (
            "title,abstract,authors,openAccessPdf,externalIds,"
            "year,citationCount"
        ),
    }
    headers = {"User-Agent": USER_AGENT}

    try:
        response = requests.get(
            API_URL,
            params=params,
            headers=headers,
            timeout=30,
        )
        if response.status_code != 200:
            print(
                f"  [S2] API error: {response.status_code}",
                file=sys.stderr,
            )
            return []
        data = response.json()
    except Exception as exc:
        print(
            f"  [S2] Request error: {exc}",
            file=sys.stderr,
        )
        return []

    sources: List[Dict] = []

    for paper in data.get("data", []):
        try:
            paper_id = str(paper.get("paperId", "")).strip()
            if not paper_id:
                continue

            source_id = "s2_" + re.sub(
                r"[^A-Za-z0-9_.-]+",
                "_",
                paper_id,
            )[:40]

            title = clean_text(paper.get("title", ""), 300)
            summary = clean_text(
                paper.get("abstract", "") or "",
                2000,
            )
            authors = [
                author.get("name", "")
                for author in paper.get("authors", [])
                if isinstance(author, dict) and author.get("name")
            ]
            year = paper.get("year")
            citation_count = paper.get("citationCount", 0)

            open_access = paper.get("openAccessPdf")
            pdf_url = None
            if isinstance(open_access, dict):
                candidate = open_access.get("url")
                if isinstance(candidate, str) and candidate.strip():
                    pdf_url = candidate.strip()

            # --------------------------------------------------------
            # Full-text cache lookup
            # --------------------------------------------------------
            cached_text = read_cache(source_id)

            full_text = ""
            status = "metadata_only"
            page_count = None

            if cached_text:
                full_text = cached_text
                status = "cached_full_text"

            elif not pdf_url:
                # No OA PDF exists, so this source is genuinely abstract-only.
                status = "abstract_only"

            else:
                try:
                    request = urllib.request.Request(
                        pdf_url,
                        headers={"User-Agent": USER_AGENT},
                    )

                    with urllib.request.urlopen(
                        request,
                        timeout=60,
                    ) as response_pdf:
                        pdf_bytes = response_pdf.read()

                    extracted_text, page_count, needs_ocr = (
                        _extract_text_from_pdf_bytes(pdf_bytes)
                    )

                    if needs_ocr:
                        print(
                            "  [S2] Scanned PDF detected, "
                            f"running OCR: {source_id}",
                            file=sys.stderr,
                        )

                        if not is_tesseract_available():
                            status = "ocr_unavailable"
                        else:
                            ocr_text, _, _ = ocr_pdf_bytes(
                                pdf_bytes,
                                dpi=300,
                            )

                            if ocr_text and len(ocr_text.split()) > 50:
                                if write_cache(source_id, ocr_text) is not None:
                                    full_text = ocr_text
                                    status = "ocr_full_text"
                                else:
                                    status = "ocr_not_cached"
                            else:
                                status = "ocr_failed"

                    elif extracted_text and len(extracted_text.split()) > 50:
                        if write_cache(source_id, extracted_text) is not None:
                            full_text = extracted_text
                            status = "parsed_full_text"
                        else:
                            status = "full_text_not_cached"
                    else:
                        status = "scanned_or_empty"

                except Exception as exc:
                    status = "pdf_download_failed"
                    print(
                        "  [S2] PDF download failed for "
                        f"{source_id}: {exc}",
                        file=sys.stderr,
                    )

            # --------------------------------------------------------
            # Evidence record
            # --------------------------------------------------------
            has_full_text = bool(full_text.strip())

            source = {
                "source_id": source_id,
                "url": (
                    pdf_url
                    or f"https://www.semanticscholar.org/paper/{paper_id}"
                ),
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "retriever_module": "research.semantic_scholar",
                "provider": "semantic_scholar",
                "query_context": query,
                "source_type": "academic",
                "content_type": "application/pdf" if pdf_url else "text/plain",
                "title": title,
                "authors": authors,
                "metadata": {
                    "abstract": summary,
                    "year": year,
                    "citation_count": citation_count,
                    "word_count": len(full_text.split()) if has_full_text else len(summary.split()),
                    "page_count": page_count,
                    "open_access_pdf_available": bool(pdf_url),
                    "full_text_available": has_full_text,
                    "full_text_status": status,
                },
                # A path is meaningful only when the text was actually cached.
                "full_text_path": (
                    str(get_cache_path(source_id))
                    if has_full_text
                    else None
                ),
                "status": status,
            }

            sources.append(source)
            time.sleep(1)

        except Exception as exc:
            print(
                f"  [S2] Error processing paper: {exc}",
                file=sys.stderr,
            )
            continue

    return sources
