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
import threading
import time
import requests
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
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

# The anonymous API has a shared, variable rate limit. Serialize search requests
# across the retrieval thread pool and retry 429 responses only a bounded number
# of times. This is a best-effort free-access policy, not a guarantee of access.
SEMANTIC_SCHOLAR_MAX_ATTEMPTS = 3
SEMANTIC_SCHOLAR_MIN_REQUEST_INTERVAL_SECONDS = 1.25
SEMANTIC_SCHOLAR_MAX_BACKOFF_SECONDS = 4.0
SEMANTIC_SCHOLAR_MAX_RETRY_AFTER_SECONDS = 15.0
_SEMANTIC_SCHOLAR_REQUEST_LOCK = threading.Lock()
_LAST_SEMANTIC_SCHOLAR_REQUEST_AT = 0.0
_SEMANTIC_SCHOLAR_COOLDOWN_UNTIL = 0.0

_RETRIEVAL_STATE = threading.local()


class _DeferredRateLimitResponse:
    """429-like response used to avoid requests during an upstream cooldown."""

    def __init__(self, remaining_seconds: float) -> None:
        self.status_code = 429
        self.headers = {"Retry-After": str(max(1, int(remaining_seconds)))}
        self.text = "Semantic Scholar request skipped because a prior Retry-After cooldown is active."


class _SearchNetworkError(requests.exceptions.RequestException):
    """Transport failure carrying the HTTP attempts already made by this query."""

    def __init__(self, cause: Exception, attempt_statuses: List[int], backoff_seconds: float) -> None:
        super().__init__(str(cause))
        self.attempt_statuses = list(attempt_statuses)
        self.attempt_count = len(attempt_statuses) + 1
        self.backoff_seconds = float(backoff_seconds)


def _set_retrieval_status(status: str, **details) -> None:
    """Record the latest provider outcome for the current worker thread."""
    record = {"status": str(status)}
    for key, value in details.items():
        if value is not None:
            record[key] = value
    _RETRIEVAL_STATE.status = record


def get_last_retrieval_status() -> Dict:
    """Return the latest Semantic Scholar retrieval outcome for this thread."""
    value = getattr(_RETRIEVAL_STATE, "status", None)
    return dict(value) if isinstance(value, dict) else {"status": "unknown"}


def _retry_after_seconds(value: str | None) -> float | None:
    """Parse Retry-After as seconds or an HTTP date; return None if invalid."""
    if not value:
        return None
    try:
        return max(0.0, float(value.strip()))
    except (TypeError, ValueError):
        pass
    try:
        target = parsedate_to_datetime(value)
        if target.tzinfo is None:
            target = target.replace(tzinfo=timezone.utc)
        return max(0.0, (target - datetime.now(timezone.utc)).total_seconds())
    except (TypeError, ValueError, OverflowError):
        return None


def _request_search_api(params: Dict, headers: Dict, timeout: int = 30):
    """Issue a paced search request with bounded, Retry-After-aware 429 retry.

    The lock intentionally covers pacing, the request and any retry wait so
    concurrent query workers cannot create a synchronized retry burst.
    Returns (response, attempt_statuses, total_backoff_seconds, stop_reason).
    """
    global _LAST_SEMANTIC_SCHOLAR_REQUEST_AT, _SEMANTIC_SCHOLAR_COOLDOWN_UNTIL
    attempt_statuses: List[int] = []
    total_backoff = 0.0
    stop_reason = None

    with _SEMANTIC_SCHOLAR_REQUEST_LOCK:
        now = time.monotonic()
        if _SEMANTIC_SCHOLAR_COOLDOWN_UNTIL > now:
            remaining = _SEMANTIC_SCHOLAR_COOLDOWN_UNTIL - now
            return _DeferredRateLimitResponse(remaining), attempt_statuses, total_backoff, "provider_cooldown_active"
        _SEMANTIC_SCHOLAR_COOLDOWN_UNTIL = 0.0
        for attempt in range(1, SEMANTIC_SCHOLAR_MAX_ATTEMPTS + 1):
            elapsed = time.monotonic() - _LAST_SEMANTIC_SCHOLAR_REQUEST_AT
            if _LAST_SEMANTIC_SCHOLAR_REQUEST_AT and elapsed < SEMANTIC_SCHOLAR_MIN_REQUEST_INTERVAL_SECONDS:
                time.sleep(SEMANTIC_SCHOLAR_MIN_REQUEST_INTERVAL_SECONDS - elapsed)

            try:
                response = requests.get(API_URL, params=params, headers=headers, timeout=timeout)
            except requests.exceptions.RequestException as exc:
                raise _SearchNetworkError(exc, attempt_statuses, total_backoff) from exc
            _LAST_SEMANTIC_SCHOLAR_REQUEST_AT = time.monotonic()
            attempt_statuses.append(int(response.status_code))

            if response.status_code != 429 or attempt >= SEMANTIC_SCHOLAR_MAX_ATTEMPTS:
                return response, attempt_statuses, round(total_backoff, 3), stop_reason

            response_headers = getattr(response, "headers", {}) or {}
            header_value = response_headers.get("Retry-After")
            retry_after = _retry_after_seconds(header_value)
            if retry_after is not None and retry_after > SEMANTIC_SCHOLAR_MAX_RETRY_AFTER_SECONDS:
                # Do not violate a long upstream Retry-After. Defer subsequent
                # queries in this process rather than issuing more requests.
                _SEMANTIC_SCHOLAR_COOLDOWN_UNTIL = time.monotonic() + retry_after
                stop_reason = "retry_after_exceeds_bounded_wait"
                return response, attempt_statuses, round(total_backoff, 3), stop_reason

            delay = retry_after if retry_after is not None else min(
                2.0 ** (attempt - 1), SEMANTIC_SCHOLAR_MAX_BACKOFF_SECONDS
            )
            if delay > 0:
                time.sleep(delay)
                total_backoff += delay

    # The loop always returns, but keep a defensive explicit failure.
    raise RuntimeError("Semantic Scholar request loop ended without a response")


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
    _set_retrieval_status(
        "starting",
        query=str(query),
        requested_results=int(max_results),
        provider="semantic_scholar",
    )

    params = {
        "query": query,
        "limit": max_results,
        "fields": (
            "title,abstract,authors,openAccessPdf,externalIds,"
            "year,citationCount"
        ),
    }
    headers = {"User-Agent": USER_AGENT}

    attempt_statuses: List[int] = []
    backoff_seconds = 0.0
    retry_stop_reason = None
    try:
        response, attempt_statuses, backoff_seconds, retry_stop_reason = _request_search_api(
            params=params,
            headers=headers,
            timeout=30,
        )
        if response.status_code != 200:
            if response.status_code == 429:
                status = "rate_limited"
            elif 400 <= response.status_code < 500:
                status = "client_error"
            elif response.status_code >= 500:
                status = "server_error"
            else:
                status = "http_error"
            _set_retrieval_status(
                status,
                provider="semantic_scholar",
                query=str(query),
                requested_results=int(max_results),
                http_status=(int(response.status_code) if retry_stop_reason != "provider_cooldown_active" else None),
                attempt_count=len(attempt_statuses),
                retry_count=max(0, len(attempt_statuses) - 1),
                http_attempt_statuses=list(attempt_statuses),
                backoff_seconds=backoff_seconds,
                retry_stop_reason=retry_stop_reason,
            )
            if retry_stop_reason == "provider_cooldown_active":
                print("  [S2] Search deferred because the upstream Retry-After cooldown is still active.", file=sys.stderr)
            else:
                print(
                    f"  [S2] API error after {len(attempt_statuses)} attempt(s): {response.status_code}",
                    file=sys.stderr,
                )
            return []
        data = response.json()
    except requests.exceptions.RequestException as exc:
        attempt_statuses = list(getattr(exc, "attempt_statuses", attempt_statuses))
        attempt_count = int(getattr(exc, "attempt_count", len(attempt_statuses) + 1))
        backoff_seconds = float(getattr(exc, "backoff_seconds", backoff_seconds))
        _set_retrieval_status(
            "network_error",
            provider="semantic_scholar",
            query=str(query),
            requested_results=int(max_results),
            attempt_count=attempt_count,
            retry_count=max(0, attempt_count - 1),
            http_attempt_statuses=list(attempt_statuses),
            backoff_seconds=backoff_seconds,
            error=str(exc),
        )
        print(
            f"  [S2] Request error: {exc}",
            file=sys.stderr,
        )
        return []
    except ValueError as exc:
        _set_retrieval_status(
            "invalid_response",
            provider="semantic_scholar",
            query=str(query),
            requested_results=int(max_results),
            attempt_count=len(attempt_statuses),
            retry_count=max(0, len(attempt_statuses) - 1),
            http_attempt_statuses=list(attempt_statuses),
            backoff_seconds=backoff_seconds,
            error=str(exc),
        )
        print(
            f"  [S2] Invalid JSON response: {exc}",
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

    _set_retrieval_status(
        "success" if sources else "empty_result",
        provider="semantic_scholar",
        query=str(query),
        requested_results=int(max_results),
        returned_records=len(sources),
        attempt_count=len(attempt_statuses),
        retry_count=max(0, len(attempt_statuses) - 1),
        http_attempt_statuses=list(attempt_statuses),
        backoff_seconds=backoff_seconds,
        retry_stop_reason=retry_stop_reason,
        records_with_oa_pdf=sum(
            1
            for item in sources
            if isinstance(item.get("metadata"), dict)
            and item["metadata"].get("open_access_pdf_available")
        ),
        records_with_full_text=sum(
            1
            for item in sources
            if item.get("full_text_path")
        ),
    )

    return sources
