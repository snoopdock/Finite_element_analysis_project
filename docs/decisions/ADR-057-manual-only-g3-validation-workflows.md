# ADR-057: Manual-Only G3 Validation Workflows

## Status
Accepted

## Decision
G3 validation workflows 05 through 12 use only GitHub Actions `workflow_dispatch`. They do not run automatically on `push` or `pull_request`.

## Rationale
Patch validation is intentionally initiated by the maintainer after review and commit/push, rather than coupled automatically to every repository update.
