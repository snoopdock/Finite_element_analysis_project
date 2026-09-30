# Milestone 06 — Projection Implementation

## Goal

Create the first semantic rendering path:

core.document_model.Document

        |

        v

DocumentModelToLatexIR

        |

        v

processing.latex_ir.DocumentModel


## Scope

This first patch:
- does not replace the legacy pipeline;
- introduces a new boundary;
- validates section and text projection.

## Future extensions

After this boundary is stable:
- CitationOccurrence -> CitationBlock
- EquationOccurrence -> MathBlock
- CrossReferenceOccurrence -> CrossReferenceBlock
