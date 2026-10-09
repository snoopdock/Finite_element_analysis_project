"""Serialization helpers for high-assurance execution records."""

from __future__ import annotations

import json
from pathlib import Path

from .models import HighAssuranceExecutionRecord


def write_high_assurance_execution(
    record: HighAssuranceExecutionRecord,
    path: str | Path,
) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(record.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    return target
