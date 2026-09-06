#!/usr/bin/env python3
"""Small integration boundary for persisting the semantic document snapshot."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Sequence, Union

from core.document_snapshot import persist_document_snapshot


DEFAULT_DOCUMENT_PATH_KEY = "document"


def persist_pipeline_document(
    state: Union[Dict[str, Any], Sequence[Dict[str, Any]]],
    paths: Union[Dict[str, Path], Path, str],
) -> Path:
    """Persist the semantic document represented by the pipeline state.

    The established contract accepts a state mapping containing ``sections``
    and a paths mapping containing ``document``. The transitional runner also
    passes the legacy section list and the destination path directly; that
    form is accepted here so the integration boundary remains compatible with
    both callers.
    """
    if isinstance(state, dict):
        sections = state.get("sections", [])
    else:
        sections = state

    if not isinstance(sections, list):
        sections = list(sections) if isinstance(sections, Sequence) else []

    if isinstance(paths, dict):
        document_path = paths.get(DEFAULT_DOCUMENT_PATH_KEY)
    else:
        document_path = paths

    if document_path is None:
        raise ValueError("Pipeline paths must define a 'document' path.")

    persist_document_snapshot(
        sections,
        document_path,
    )
    return Path(document_path)
