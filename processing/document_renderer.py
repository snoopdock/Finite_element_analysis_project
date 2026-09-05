#!/usr/bin/env python3
"""Rendering boundary for structured documents.

This module deliberately contains the public renderer contract first. The
legacy LaTeX builder remains the compatibility implementation until the
individual rendering operations are migrated behind this boundary.
"""

from typing import Any, Mapping, Sequence


def render_document(
    state: Mapping[str, Any],
    sections: Sequence[Mapping[str, Any]],
    evidence: Sequence[Mapping[str, Any]],
) -> str:
    """Render a structured document through the compatibility boundary.

    The function preserves the existing pipeline contract while establishing
    a single entry point for the future node-oriented renderer. Keeping the
    import local avoids an import cycle during the migration.
    """
    from processing.latex_builder import build_latex_document

    return build_latex_document(state, sections, evidence)
