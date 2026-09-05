#!/usr/bin/env python3
"""Persistence boundary for the semantic document model.

The persisted representation is the document model's serialized form. This
module deliberately performs no semantic inference and does not modify the
legacy sections representation.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from core.document_model import Document, DocumentModelError, document_from_legacy_sections


class DocumentPersistenceError(DocumentModelError):
    """Raised when a semantic document cannot be persisted or loaded safely."""


def save_document(document: Document, path: Path) -> None:
    """Validate and atomically persist a semantic document as JSON."""
    if not isinstance(document, Document):
        raise DocumentPersistenceError("Expected a Document instance.")

    payload = document.to_dict()
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")

    try:
        temporary.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        temporary.replace(destination)
    except OSError as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise DocumentPersistenceError(
            f"Failed to persist semantic document: {exc}"
        ) from exc


def load_document(path: Path) -> Optional[Dict[str, Any]]:
    """Load persisted semantic document JSON without guessing missing structure.

    The current increment exposes the persisted JSON payload directly. A typed
    deserializer will be added only when the model requires round-trip loading
    by the pipeline; avoiding a partial deserializer here prevents silent data
    loss.
    """
    source = Path(path)
    if not source.exists():
        return None

    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DocumentPersistenceError(
            f"Failed to load semantic document: {exc}"
        ) from exc

    if not isinstance(payload, dict):
        raise DocumentPersistenceError("Persisted semantic document must be a JSON object.")
    return payload


def build_document_from_legacy_sections(
    sections: Sequence[Dict[str, Any]],
    *,
    document_id: Optional[str] = None,
) -> Document:
    """Build the first persisted document snapshot from legacy sections."""
    return document_from_legacy_sections(
        sections,
        document_id=document_id,
    )
