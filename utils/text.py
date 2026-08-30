#!/usr/bin/env python3
"""Text processing utilities."""

import datetime
import json
import pathlib
import re
import os
import tempfile
import yaml


def utcnow():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def ensure_base_dirs(root: pathlib.Path):
    (root / "output").mkdir(parents=True, exist_ok=True)
    (root / "state").mkdir(parents=True, exist_ok=True)


def load_yaml(path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_json(path, default):
    path = pathlib.Path(path)
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, obj):
    """Save object as JSON file using atomic writes to prevent corruption."""
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    
    # Write to a temporary file in the same directory, then atomically replace
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, path)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def save_text(path, text):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def clean_text(s, limit=2000):
    if not s:
        return ""
    s = re.sub(r"\s+", " ", str(s)).strip()
    return s[:limit]


def truncate_text(s, limit):
    """Truncate plain text with ellipsis. NOT safe for JSON."""
    s = str(s)
    if len(s) <= limit:
        return s
    return s[:limit] + "\n... [truncated]"


def truncate_json_safe(kb: dict, max_items_per_category: int = 5) -> dict:
    """
    Truncate a knowledge base dict by limiting items per category.
    Returns a valid dict (not a string), safe for json.loads.
    This preserves JSON structure while reducing size for LLM prompts.
    """
    truncated = {}
    for category in ["concepts", "procedures", "equations", "rules"]:
        items = kb.get(category, [])
        truncated[category] = items[:max_items_per_category]
    return truncated


def kb_to_prompt_text(kb: dict, max_chars: int = 6000) -> str:
    """
    Convert knowledge base to a truncated text string for LLM prompts.
    This is for display only. Never pass this to json.loads.
    """
    lines = []
    for category in ["concepts", "procedures", "equations", "rules"]:
        items = kb.get(category, [])
        if items:
            lines.append(f"=== {category.upper()} ({len(items)} items) ===")
            for item in items[:5]:
                if isinstance(item, dict):
                    name = item.get("name") or item.get("title") or item.get("rule", "Unknown")
                    explanation = item.get("explanation") or item.get("description", "")
                    lines.append(f"- {name}: {explanation[:200]}")
            lines.append("")
    
    result = "\n".join(lines)
    if len(result) > max_chars:
        result = result[:max_chars] + "\n... [truncated]"
    return result
