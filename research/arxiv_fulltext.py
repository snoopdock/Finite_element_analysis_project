#!/usr/bin/env python3
"""arXiv full-text retrieval with bounded local text caching."""

import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Dict, List

from utils.text import clean_text
from research.content_cache import (
    get_cache_path,
    read_cache,
    write_cache,
)
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


def _extract_text_from_pdf_bytes(pdf_bytes: bytes) -> tuple:
    """Extract PDF text and indicate whether OCR is required."""
    text_pages = []
    page_count = 0

    try:
        import pymupdf

        with pymupdf.open(
            stream=pdf_bytes,
            filetype="pdf",
        ) as doc:
            page_count = len(doc)
            for page in doc:
                text_pages.append(page.get_text())

    except Exception as exc:
        print(
            f"  [arXiv] PDF parse error: {exc}",
            file=sys.stderr,
        )
        return "", 0, True

    full_text = "\n".join(text_pages)
    needs_ocr = should_run_ocr(
        full_text,
        page_count,
    )

    return (
        full_text,
        page_count,
        needs_ocr,
    )


def _cache_full_text(
    source_id: str,
    text: str,
):
    """Cache text and return a valid path when it remains cached."""
    return write_cache(
        source_id,
        text,
    )


def search_arxiv(
    query: str,
    max_results: int = 3,
) -> List[Dict]:
    """Search arXiv and retrieve actual PDF text when available."""

    url = "https://export.arxiv.org/api/query"

    params = {
        "search_query": f"all:{query}",
        "start": 0,
        "max_results": max_results,
        "sortBy": "relevance",
    }

    req = urllib.request.Request(
        url
        + "?"
        + urllib.parse.urlencode(params),
        headers={
            "User-Agent": USER_AGENT,
        },
    )

    try:
        with urllib.request.urlopen(
            req,
            timeout=30,
        ) as response:
            xml_data = response.read()

    except Exception as exc:
        print(
            f"  [arXiv] API error: {exc}",
            file=sys.stderr,
        )
        return []

    root = ET.fromstring(xml_data)
    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "arxiv": "http://arxiv.org/schemas/atom",
    }

    sources = []

    for entry in root.findall(
        "atom:entry",
        ns,
    ):
        try:
            id_element = entry.find(
                "atom:id",
                ns,
            )
            id_text = (
                id_element.text.strip()
                if id_element is not None
                and id_element.text
                else ""
            )

            uid = id_text.split(
                "/abs/"
            )[-1]

            source_id = (
                "arxiv_"
                + re.sub(
                    r"[^a-zA-Z0-9_.]+",
                    "_",
                    uid,
                )
            )

            title_element = entry.find(
                "atom:title",
                ns,
            )
            summary_element = entry.find(
                "atom:summary",
                ns,
            )
            published_element = entry.find(
                "atom:published",
                ns,
            )

            title = clean_text(
                title_element.text
                if title_element is not None
                else "",
                300,
            )

            summary = clean_text(
                summary_element.text
                if summary_element is not None
                else "",
                2000,
            )

            authors = [
                author.find(
                    "atom:name",
                    ns,
                ).text
                for author in entry.findall(
                    "atom:author",
                    ns,
                )
                if author.find(
                    "atom:name",
                    ns,
                ) is not None
                and author.find(
                    "atom:name",
                    ns,
                ).text
            ]

            published = (
                published_element.text
                if published_element is not None
                else ""
            )

            pdf_url = (
                f"https://arxiv.org/pdf/{uid}.pdf"
            )

            # --------------------------------------------------------
            # Cache lookup
            # --------------------------------------------------------

            cached_text = read_cache(
                source_id
            )

            full_text = ""
            full_text_path = None

            if cached_text:
                full_text = cached_text
                full_text_path = str(
                    get_cache_path(source_id)
                )
                status = "cached_full_text"

            else:
                status = "metadata_only"

                try:
                    req_pdf = urllib.request.Request(
                        pdf_url,
                        headers={
                            "User-Agent": USER_AGENT,
                        },
                    )

                    with urllib.request.urlopen(
                        req_pdf,
                        timeout=60,
                    ) as response_pdf:
                        pdf_bytes = response_pdf.read()

                    (
                        extracted_text,
                        page_count,
                        needs_ocr,
                    ) = _extract_text_from_pdf_bytes(
                        pdf_bytes
                    )

                    if needs_ocr:
                        print(
                            "  [arXiv] Scanned PDF detected, "
                            f"running OCR: {uid}",
                            file=sys.stderr,
                        )

                        if is_tesseract_available():
                            ocr_text, _, _ = (
                                ocr_pdf_bytes(
                                    pdf_bytes,
                                    dpi=300,
                                )
                            )

                            if (
                                ocr_text
                                and len(
                                    ocr_text.split()
                                )
                                > 50
                            ):
                                full_text = ocr_text
                                cached_path = (
                                    _cache_full_text(
                                        source_id,
                                        full_text,
                                    )
                                )

                                if cached_path:
                                    full_text_path = str(
                                        cached_path
                                    )
                                    status = "ocr_full_text"
                                else:
                                    status = "ocr_full_text_uncached"

                            else:
                                status = "ocr_failed"

                        else:
                            status = "ocr_unavailable"
                            print(
                                "  [arXiv] Tesseract not installed, "
                                "skipping OCR",
                                file=sys.stderr,
                            )

                    else:
                        if (
                            extracted_text
                            and len(
                                extracted_text.split()
                            )
                            > 50
                        ):
                            full_text = extracted_text
                            cached_path = (
                                _cache_full_text(
                                    source_id,
                                    full_text,
                                )
                            )

                            if cached_path:
                                full_text_path = str(
                                    cached_path
                                )
                                status = "parsed_full_text"
                            else:
                                status = "parsed_full_text_uncached"

                        else:
                            status = "scanned_or_empty"

                    # Respect arXiv API/download pacing.
                    time.sleep(3)

                except Exception as exc:
                    print(
                        f"  [arXiv] Download failed for {uid}: {exc}",
                        file=sys.stderr,
                    )

            sources.append(
                {
                    "source_id": source_id,
                    "url": pdf_url,
                    "retrieved_at": datetime.now(
                        timezone.utc
                    ).isoformat(),
                    "retriever_module": (
                        "research.arxiv_fulltext"
                    ),
                    "provider": "arxiv",
                    "source_type": "arxiv",
                    "content_type": "application/pdf",
                    "title": title,
                    "authors": authors,
                    "metadata": {
                        "abstract": summary,
                        "published": published,
                        "page_count": page_count
                        if 'page_count' in locals()
                        else 0,
                        "word_count": (
                            len(full_text.split())
                            if full_text
                            else len(summary.split())
                        ),
                    },
                    "full_text_path": full_text_path,
                    "full_text_available": bool(
                        full_text_path
                    ),
                    "status": status,
                }
            )

        except Exception as exc:
            print(
                "  [arXiv] Error processing entry: "
                f"{exc}",
                file=sys.stderr,
            )
            continue

    return sources
