#!/usr/bin/env python3
"""Build and persist a semantic document snapshot from pipeline sections."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from core.document_model import Document
from core.document_persistence import save_document, build_document_from_legacy_sections


def build_document_snapshot(
    sections: Sequence[Dict[str, Any]],
    *,
    document_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Document:
    """Construct a semantic document snapshot without semantic inference."""
    document = build_document_from_legacy_sections(
        sections,
        document_id=document_id,
    )
    if metadata:
        document.metadata.update(dict(metadata))
    return document


def persist_document_snapshot(
    sections: Sequence[Dict[str, Any]],
    path: Path,
    *,
    document_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Document:
    """Build and persist a semantic snapshot, returning the typed document."""
    document = build_document_snapshot(
        sections,
        document_id=document_id,
        metadata=metadata,
    )
    save_document(document, path)
    return document
