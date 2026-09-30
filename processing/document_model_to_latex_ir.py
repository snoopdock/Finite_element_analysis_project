"""
Milestone 06 - Semantic Document -> LaTeX IR Projection

This module introduces the first semantic rendering boundary.

Purpose:
    core.document_model.Document
            |
            v
    processing.latex_ir.DocumentModel

This first implementation intentionally keeps the transformation narrow:
- preserve section order
- preserve text content
- preserve occurrence identifiers where supported

It does not replace the existing legacy pipeline.
"""

from processing.latex_ir import (
    DocumentModel,
    SectionModel,
    TextBlock,
)


class DocumentModelToLatexIR:
    """
    Semantic document projection adapter.
    """

    def project(self, document):
        sections = []

        for child in getattr(document, "children", []):
            section = self._project_section(child)
            if section is not None:
                sections.append(section)

        return DocumentModel(
            topic=getattr(document, "metadata", {}).get("topic", ""),
            objective=getattr(document, "metadata", {}).get("objective", ""),
            sections=tuple(sections),
            references=tuple(),
        )

    def _project_section(self, section):
        blocks = []

        for child in getattr(section, "children", []):
            block = self._project_child(child)
            if block is not None:
                blocks.append(block)

        return SectionModel(
            title=getattr(section, "title", ""),
            blocks=tuple(blocks),
        )

    def _project_child(self, child):
        """
        First implementation supports text-like objects.

        Additional semantic objects (citation, equation, cross-reference)
        should be added after validating their IR counterparts.
        """

        content = getattr(child, "text", None)

        if content is None:
            content = getattr(child, "content", None)

        if content is not None:
            return TextBlock(text=content)

        return None
