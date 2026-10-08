"""Serialization helpers for G3.2 evolution artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_json_artifact(payload: Any, path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if hasattr(payload, 'to_dict'):
        payload = payload.to_dict()
    target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding='utf-8')
