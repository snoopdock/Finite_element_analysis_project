#!/usr/bin/env python3
"""Bounded local cache for downloaded article full text.

The cache is application-local and gitignored. It stores extracted article
text rather than PDF binaries, allowing the research layer to inspect the
actual article while keeping persistent repository history small.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional


APP_ROOT = Path(__file__).resolve().parents[1]
RAW_TEXT_DIR = APP_ROOT / "output" / "raw_text"
CACHE_INDEX_FILE = RAW_TEXT_DIR / "_cache_index.json"

DEFAULT_MAX_SIZE_MB = 500


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_cache_dir() -> None:
    RAW_TEXT_DIR.mkdir(parents=True, exist_ok=True)


def get_max_cache_size_kb() -> int:
    """Return configured cache size in KB.

    ``FEA_CACHE_MAX_SIZE_MB`` is an optional environment override. The
    repository configuration remains the preferred user-facing setting; the
    environment variable is useful for CI.
    """
    raw = os.environ.get("FEA_CACHE_MAX_SIZE_MB", "")
    if raw.strip():
        try:
            value = float(raw)
            if value > 0:
                return int(value * 1024)
        except ValueError:
            pass

    return DEFAULT_MAX_SIZE_MB * 1024


def get_cache_path(source_id: str) -> Path:
    ensure_cache_dir()
    safe_id = str(source_id).strip()
    if not safe_id:
        raise ValueError("source_id cannot be empty")
    return RAW_TEXT_DIR / f"{safe_id}.txt"


def _load_index() -> Dict:
    if not CACHE_INDEX_FILE.exists():
        return {}

    try:
        with open(
            CACHE_INDEX_FILE,
            "r",
            encoding="utf-8",
        ) as handle:
            data = json.load(handle)
    except (
        OSError,
        json.JSONDecodeError,
    ):
        return {}

    if not isinstance(data, dict):
        return {}

    return data


def _save_index(index: Dict) -> None:
    ensure_cache_dir()

    fd, tmp_path = tempfile.mkstemp(
        dir=RAW_TEXT_DIR,
        suffix=".tmp",
    )

    try:
        with os.fdopen(
            fd,
            "w",
            encoding="utf-8",
        ) as handle:
            json.dump(
                index,
                handle,
                indent=2,
                ensure_ascii=False,
            )
            handle.flush()
            os.fsync(handle.fileno())

        os.replace(
            tmp_path,
            CACHE_INDEX_FILE,
        )

    except Exception:
        try:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
        except OSError:
            pass
        raise


def read_cache(source_id: str) -> Optional[str]:
    """Read cached text and update its access time for LRU eviction."""
    path = get_cache_path(source_id)

    if not path.exists():
        return None

    try:
        with open(
            path,
            "r",
            encoding="utf-8",
        ) as handle:
            text = handle.read()
    except OSError as exc:
        print(
            f"  [Cache] Error reading {source_id}: {exc}",
            file=os.sys.stderr,
        )
        return None

    index = _load_index()
    metadata = index.get(source_id, {})
    metadata.update(
        {
            "size_bytes": path.stat().st_size,
            "size_kb": round(path.stat().st_size / 1024, 2),
            "cached_at": metadata.get("cached_at", _now()),
            "last_accessed_at": _now(),
        }
    )
    index[source_id] = metadata

    try:
        _save_index(index)
    except Exception:
        # Reading cached text must not fail because the bookkeeping file
        # could not be updated.
        pass

    return text


def write_cache(
    source_id: str,
    text: str,
    max_size_kb: Optional[int] = None,
) -> Optional[Path]:
    """Atomically cache extracted text and enforce the size bound.

    Returns the cache path when the item remains cached, otherwise ``None``.
    """
    ensure_cache_dir()

    if not isinstance(text, str) or not text.strip():
        return None

    encoded_size = len(text.encode("utf-8"))
    limit_kb = (
        int(max_size_kb)
        if max_size_kb is not None
        else get_max_cache_size_kb()
    )
    limit_bytes = max(1, limit_kb) * 1024

    # Never exceed the cache bound, even for one enormous article.
    if encoded_size > limit_bytes:
        print(
            f"  [Cache] Skipping {source_id}: "
            f"item size {encoded_size / (1024 * 1024):.1f} MB "
            f"exceeds cache limit {limit_bytes / (1024 * 1024):.1f} MB.",
            file=os.sys.stderr,
        )
        return None

    path = get_cache_path(source_id)
    fd, tmp_path = tempfile.mkstemp(
        dir=RAW_TEXT_DIR,
        suffix=".tmp",
    )

    try:
        with os.fdopen(
            fd,
            "w",
            encoding="utf-8",
        ) as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())

        os.replace(
            tmp_path,
            path,
        )

    except Exception as exc:
        try:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
        except OSError:
            pass

        print(
            f"  [Cache] Error writing {source_id}: {exc}",
            file=os.sys.stderr,
        )
        return None

    index = _load_index()
    index[source_id] = {
        "cached_at": _now(),
        "last_accessed_at": _now(),
        "size_bytes": encoded_size,
        "size_kb": round(encoded_size / 1024, 2),
    }

    try:
        _save_index(index)
    except Exception as exc:
        print(
            f"  [Cache] Index update failed for {source_id}: {exc}",
            file=os.sys.stderr,
        )

    cleanup_cache(limit_kb)

    if not path.exists():
        return None

    return path


def cleanup_cache(
    max_size_kb: Optional[int] = None,
) -> Dict:
    """Enforce the maximum cache size using least-recently-used eviction."""
    limit_kb = (
        int(max_size_kb)
        if max_size_kb is not None
        else get_max_cache_size_kb()
    )

    limit_kb = max(1, limit_kb)
    index = _load_index()

    # Reconcile the index with actual files. This also repairs stale entries
    # left behind by interrupted runs or manual deletion.
    for source_id in list(index):
        path = RAW_TEXT_DIR / f"{source_id}.txt"
        if not path.exists():
            del index[source_id]
            continue

        actual_size = path.stat().st_size
        index[source_id]["size_bytes"] = actual_size
        index[source_id]["size_kb"] = round(actual_size / 1024, 2)
        index[source_id].setdefault(
            "cached_at",
            _now(),
        )
        index[source_id].setdefault(
            "last_accessed_at",
            index[source_id]["cached_at"],
        )

    # Include orphaned .txt files not represented in the index.
    for path in RAW_TEXT_DIR.glob("*.txt"):
        source_id = path.stem
        if source_id not in index:
            timestamp = datetime.fromtimestamp(
                path.stat().st_mtime,
                tz=timezone.utc,
            ).isoformat()
            index[source_id] = {
                "cached_at": timestamp,
                "last_accessed_at": timestamp,
                "size_bytes": path.stat().st_size,
                "size_kb": round(
                    path.stat().st_size / 1024,
                    2,
                ),
            }

    def total_kb() -> float:
        return sum(
            float(meta.get("size_kb", 0))
            for meta in index.values()
        )

    total = total_kb()

    if total > limit_kb:
        candidates = sorted(
            index.items(),
            key=lambda pair: (
                pair[1].get(
                    "last_accessed_at",
                    pair[1].get("cached_at", ""),
                ),
                pair[1].get("cached_at", ""),
            ),
        )

        for source_id, metadata in candidates:
            if total <= limit_kb:
                break

            path = RAW_TEXT_DIR / f"{source_id}.txt"

            try:
                if path.exists():
                    path.unlink()
            except OSError as exc:
                print(
                    f"  [Cache] Could not evict {source_id}: {exc}",
                    file=os.sys.stderr,
                )
                continue

            total -= float(
                metadata.get(
                    "size_kb",
                    0,
                )
            )
            del index[source_id]

    try:
        _save_index(index)
    except Exception as exc:
        print(
            f"  [Cache] Index save failed during cleanup: {exc}",
            file=os.sys.stderr,
        )

    return get_cache_stats()


def get_cache_stats() -> Dict:
    """Return reconciled cache statistics."""
    index = _load_index()

    total_bytes = 0
    valid_files = 0

    for source_id in list(index):
        path = RAW_TEXT_DIR / f"{source_id}.txt"
        if not path.exists():
            continue
        try:
            total_bytes += path.stat().st_size
            valid_files += 1
        except OSError:
            continue

    return {
        "total_files": valid_files,
        "total_size_bytes": total_bytes,
        "total_size_kb": round(
            total_bytes / 1024,
            2,
        ),
        "total_size_mb": round(
            total_bytes / (1024 * 1024),
            2,
        ),
        "max_size_kb": get_max_cache_size_kb(),
        "max_size_mb": round(
            get_max_cache_size_kb() / 1024,
            2,
        ),
        "files": index,
    }
