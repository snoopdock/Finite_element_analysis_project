#!/usr/bin/env python3
"""Helpers for attaching retrieval-cycle provenance to pipeline state."""

from __future__ import annotations

from copy import deepcopy
from typing import Dict


def attach_retrieval_report(state: Dict, report: Dict) -> Dict:
    """Return state with the latest retrieval-cycle report attached.

    Retrieval status describes the operation that was attempted. It must not
    be interpreted as a scientific judgment about the literature itself.
    """
    updated = dict(state) if isinstance(state, dict) else {}
    updated["retrieval_report"] = deepcopy(report) if isinstance(report, dict) else {
        "status": "unknown",
    }
    return updated


def get_retrieval_status(state: Dict) -> str:
    """Return the last recorded retrieval-cycle status, or ``unknown``."""
    if not isinstance(state, dict):
        return "unknown"
    report = state.get("retrieval_report")
    if not isinstance(report, dict):
        return "unknown"
    status = report.get("status")
    return str(status).strip() if status else "unknown"
