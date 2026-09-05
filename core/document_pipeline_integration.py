#!/usr/bin/env python3
"""Small integration boundary for persisting the semantic document snapshot."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Sequence

from core.document_snapshot import persist_document_snapshot


DEFAULT_DOCUMENT_PATH_KEY = "document"


def persist_pipeline_document(
    state: Dict[str, Any],
    paths: Dict[str, Path],
) -> Path:
    """Persist the semantic document represented by ``state['sections']``.

    This helper is intentionally side-effect limited: it reads the current
    legacy section list, creates the semantic snapshot, and writes it to the
    configured document path. It does not replace ``state['sections']`` and it
    does not modify the legacy ``sections.json`` artifact.
    """
    sections = state.get("sections", [])
    if not isinstance(sections, list):
        sections = []

    document_path = paths.get(DEFAULT_DOCUMENT_PATH_KEY)
    if document_path is None:
        raise ValueError("Pipeline paths must define a 'document' path.")

    persist_document_snapshot(
        sections,
        document_path,
    )
    return Path(document_path)
