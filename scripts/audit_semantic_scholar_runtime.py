#!/usr/bin/env python3
"""Runtime diagnostic for the Semantic Scholar retrieval path.

This audit exercises the existing Semantic Scholar retriever and reports the
provider outcome separately from the number of records returned. It performs
network I/O, does not call an LLM, and does not modify tracked repository files.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.content_cache import get_cache_path  # noqa: E402
from research.semantic_scholar import (  # noqa: E402
    get_last_retrieval_status,
    search_semantic_scholar,
)
from utils.text import load_json  # noqa: E402

DEFAULT_QUERY = "finite element method mathematical foundation weak form Galerkin method"
EVIDENCE_PATH = ROOT / "output" / "evidence.json"


def _bool_text(value: bool) -> str:
    return "yes" if value else "no"


def _persisted_semantic_scholar_records() -> list[dict]:
    data = load_json(EVIDENCE_PATH, [])
    if not isinstance(data, list):
        return []

    records = []
    for item in data:
        if not isinstance(item, dict):
            continue
        providers = item.get("provider_names", [])
        provider = str(item.get("provider", ""))
        retriever = str(item.get("retriever_module", ""))
        if (
            provider == "semantic_scholar"
            or "semantic_scholar" in retriever
            or (
                isinstance(providers, list)
                and "semantic_scholar" in providers
            )
        ):
            records.append(item)
    return records


def _print_source(index: int, source: dict) -> None:
    source_id = str(source.get("source_id", ""))
    metadata = source.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}

    cache_path = source.get("full_text_path")
    cache_exists = bool(
        cache_path
        and isinstance(cache_path, str)
        and os.path.exists(cache_path)
    )

    canonical_cache_path = None
    if source_id:
        try:
            canonical_cache_path = get_cache_path(source_id)
        except ValueError:
            canonical_cache_path = None

    print(f"\n  Source {index}: {source.get('title', 'Untitled')}")
    print(f"    source_id: {source_id or 'missing'}")
    print(f"    provider: {source.get('provider', 'unknown')}")
    print(f"    retriever_module: {source.get('retriever_module', 'unknown')}")
    print(f"    status: {source.get('status', 'unknown')}")
    print(f"    open_access_pdf_available: {_bool_text(bool(metadata.get('open_access_pdf_available')))}")
    print(f"    full_text_available: {_bool_text(bool(metadata.get('full_text_available')))}")
    print(f"    full_text_status: {metadata.get('full_text_status', source.get('status', 'unknown'))}")
    print(f"    full_text_path_recorded: {_bool_text(bool(cache_path))}")
    print(f"    recorded_cache_exists: {_bool_text(cache_exists)}")
    print(f"    canonical_cache_path: {canonical_cache_path or 'n/a'}")
    print(f"    url: {source.get('url', 'missing')}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect the live Semantic Scholar retrieval path."
    )
    parser.add_argument(
        "query",
        nargs="?",
        default=DEFAULT_QUERY,
        help="Semantic Scholar query to run once.",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=3,
        help="Maximum papers requested from Semantic Scholar (default: 3).",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.max_results < 1:
        print("max-results must be >= 1", file=sys.stderr)
        return 2

    print("=== SEMANTIC SCHOLAR RUNTIME AUDIT ===")
    print(f"Repository root: {ROOT}")
    print(f"Query: {args.query}")
    print(f"Requested results: {args.max_results}")
    print("\n--- Live retriever ---")

    try:
        sources = search_semantic_scholar(
            args.query,
            max_results=args.max_results,
        )
    except Exception as exc:
        print(f"Retriever raised {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    retrieval_status = get_last_retrieval_status()
    print(f"Provider status: {retrieval_status.get('status', 'unknown')}")
    for key in (
        "http_status",
        "returned_records",
        "records_with_oa_pdf",
        "records_with_full_text",
        "error",
    ):
        if key in retrieval_status:
            print(f"  {key}: {retrieval_status[key]}")

    print(f"Returned source records: {len(sources)}")

    if not sources:
        print("No records returned by the current Semantic Scholar retriever.")
        print("The provider status above distinguishes an empty search from a failure when available.")
    else:
        for index, source in enumerate(sources, start=1):
            if isinstance(source, dict):
                _print_source(index, source)

    full_text_count = sum(
        1
        for item in sources
        if isinstance(item, dict)
        and bool(item.get("full_text_path"))
    )
    oa_pdf_count = sum(
        1
        for item in sources
        if isinstance(item, dict)
        and isinstance(item.get("metadata"), dict)
        and bool(item["metadata"].get("open_access_pdf_available"))
    )
    cached_count = sum(
        1
        for item in sources
        if isinstance(item, dict)
        and bool(
            item.get("full_text_path")
            and os.path.exists(str(item.get("full_text_path")))
        )
    )

    print("\n--- Retrieval stage summary ---")
    print(f"API/search records returned: {len(sources)}")
    print(f"Records with OA PDF advertised: {oa_pdf_count}")
    print(f"Records with full-text path: {full_text_count}")
    print(f"Records with existing local cache file: {cached_count}")

    print("\n--- Persisted evidence ---")
    persisted = _persisted_semantic_scholar_records()
    print(f"Semantic Scholar records currently in output/evidence.json: {len(persisted)}")

    for index, source in enumerate(persisted[:10], start=1):
        print(
            f"  {index}. {source.get('source_id', 'missing')} | "
            f"{source.get('title', 'Untitled')} | "
            f"status={source.get('status', 'unknown')}"
        )

    print("\nInterpretation:")
    status = retrieval_status.get("status", "unknown")
    if status == "rate_limited":
        print("  LIVE RESULT: Semantic Scholar responded with HTTP 429 rate limiting.")
    elif status in {"network_error", "server_error", "client_error", "http_error", "invalid_response"}:
        print(f"  LIVE RESULT: Semantic Scholar provider failed with status '{status}'.")
    elif status == "empty_result":
        print("  LIVE RESULT: Semantic Scholar completed successfully but returned no usable source records.")
    elif status == "success":
        print("  LIVE RESULT: Semantic Scholar returned source records successfully.")
    else:
        print(f"  LIVE RESULT: provider outcome is '{status}'.")

    if persisted:
        print("  PERSISTED RESULT: Semantic Scholar provenance exists in output/evidence.json.")
    else:
        print("  PERSISTED RESULT: no Semantic Scholar provenance record was found in output/evidence.json.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
