#!/usr/bin/env python3
"""Runtime diagnostic for the Semantic Scholar retrieval path.

This audit intentionally exercises the existing Semantic Scholar retriever
rather than changing its behavior. It reports each observable stage:
API result count, open-access PDF availability, local full-text availability,
cache path state, and persisted evidence provenance when available.

The script performs network I/O and should be run manually from the repository
root. It does not call an LLM or modify tracked repository files.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.content_cache import get_cache_path  # noqa: E402
from research.semantic_scholar import search_semantic_scholar  # noqa: E402
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

    print(f"Returned source records: {len(sources)}")

    if not sources:
        print("No records returned by the current Semantic Scholar retriever.")
        print("This does not distinguish 'no results' from an API/provider failure;")
        print("the runtime logs above must be inspected together with this result.")
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
    if not sources:
        print("  LIVE RESULT: no source records reached the caller.")
        print("  Check the [S2] HTTP error lines immediately above this report.")
    elif full_text_count == 0:
        print("  LIVE RESULT: Semantic Scholar returned records, but no full-text path was produced.")
    elif cached_count == 0:
        print("  LIVE RESULT: full-text paths were reported, but no corresponding cache files exist now.")
    else:
        print("  LIVE RESULT: at least one Semantic Scholar record reached local full-text caching.")

    if persisted:
        print("  PERSISTED RESULT: Semantic Scholar provenance exists in output/evidence.json.")
    else:
        print("  PERSISTED RESULT: no Semantic Scholar provenance record was found in output/evidence.json.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
