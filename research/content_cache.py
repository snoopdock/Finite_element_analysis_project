#!/usr/bin/env python3
"""
Content Cache Manager
Stores raw text in a gitignored directory.
"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict

RAW_TEXT_DIR = Path("output/raw_text")
CACHE_INDEX_FILE = RAW_TEXT_DIR / "_cache_index.json"


def ensure_cache_dir():
    RAW_TEXT_DIR.mkdir(parents=True, exist_ok=True)


def get_cache_path(source_id: str) -> Path:
    ensure_cache_dir()
    return RAW_TEXT_DIR / f"{source_id}.txt"


def read_cache(source_id: str) -> Optional[str]:
    path = get_cache_path(source_id)
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            print(f"  [Cache] Error reading {source_id}: {e}", file=sys.stderr)
    return None


def write_cache(source_id: str, text: str) -> Path:
    ensure_cache_dir()
    path = get_cache_path(source_id)
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        _update_cache_index(source_id, len(text))
        return path
    except Exception as e:
        print(f"  [Cache] Error writing {source_id}: {e}", file=sys.stderr)
        return path


def _update_cache_index(source_id: str, size_bytes: int):
    ensure_cache_dir()
    index = {}
    if CACHE_INDEX_FILE.exists():
        try:
            with open(CACHE_INDEX_FILE, "r", encoding="utf-8") as f:
                index = json.load(f)
        except Exception:
            index = {}

    index[source_id] = {
        "cached_at": datetime.now(timezone.utc).isoformat(),
        "size_bytes": size_bytes,
        "size_kb": round(size_bytes / 1024, 2)
    }

    try:
        with open(CACHE_INDEX_FILE, "w", encoding="utf-8") as f:
            json.dump(index, f, indent=2)
    except Exception:
        pass


def cleanup_cache(max_size_kb: int = 5000):
    """Remove oldest cached files if total size exceeds max_size_kb."""
    stats = get_cache_stats()
    if stats["total_size_kb"] <= max_size_kb:
        return

    try:
        with open(CACHE_INDEX_FILE, "r", encoding="utf-8") as f:
            index = json.load(f)
    except Exception:
        return

    sorted_entries = sorted(index.items(), key=lambda x: x[1].get("cached_at", ""))

    while stats["total_size_kb"] > max_size_kb and sorted_entries:
        source_id, meta = sorted_entries.pop(0)
        path = get_cache_path(source_id)
        if path.exists():
            path.unlink()
        if source_id in index:
            stats["total_size_kb"] -= meta.get("size_kb", 0)
            del index[source_id]

    try:
        with open(CACHE_INDEX_FILE, "w", encoding="utf-8") as f:
            json.dump(index, f, indent=2)
    except Exception:
        pass


def get_cache_stats() -> Dict:
    if not CACHE_INDEX_FILE.exists():
        return {"total_files": 0, "total_size_kb": 0}

    try:
        with open(CACHE_INDEX_FILE, "r", encoding="utf-8") as f:
            index = json.load(f)
    except Exception:
        return {"total_files": 0, "total_size_kb": 0}

    total_size = sum(entry.get("size_kb", 0) for entry in index.values())
    return {
        "total_files": len(index),
        "total_size_kb": round(total_size, 2),
        "files": index
    }
