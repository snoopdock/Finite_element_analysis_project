# Milestone 06 — Semantic Rendering Validation

## Phase
Discovery phase.

## Purpose
Discover the real repository interfaces before implementing the semantic rendering adapter.

Target boundary:

core.document_model.Document
        |
        v
Document to LaTeX IR projection
        |
        v
processing.latex_ir.DocumentModel

## Current action
This package only adds discovery tests and a GitHub workflow.
No production code is modified.

## Expected output
The workflow log should show:
- document model classes and signatures
- LaTeX IR classes and signatures
- pipeline functions and signatures

After reviewing the logs, the next implementation package will contain the real adapter.
