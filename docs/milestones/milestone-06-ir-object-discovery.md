# Milestone 06 — IR Object Discovery

## Purpose

Determine whether semantic occurrence objects already have matching
representations in `processing.latex_ir`.

Target objects:

- CitationBlock
- MathBlock
- CrossReferenceBlock
- DocumentBlock
- TextBlock
- SectionModel
- DocumentModel

## Reason

The next projection step depends on whether the renderer IR already
supports semantic objects.

No production code is changed in this phase.

## Next step

Use the workflow log to decide whether to:

1. extend the existing adapter only, or
2. add minimal IR object support first.
