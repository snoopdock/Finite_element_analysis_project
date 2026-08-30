# Sequential Architecture Update Report

## Stage 1 — Stable section identity

Implemented a UUID-based identity layer for document sections. State schema is v4. Existing valid section IDs are preserved; missing or duplicate IDs are repaired. Split sections receive new child IDs and parent lineage; merged sections receive a new ID with both parent IDs.

## Stage 2 — OAA and writer identity integration

Writing history and OAA anomaly keys now prefer section UUIDs instead of mutable titles. Rewrites preserve section IDs. OAA actions locate sections by UUID. Split and merge operations maintain lineage and document order.

## Stage 3 — Evidence provenance and ranking

Added `research/ranking.py`. Retrieval now records exact provider and originating query for each source. Evidence selection is ranked deterministically instead of depending on asynchronous completion order. The writer consumes ranked knowledge-base items.

## Stage 4 — LLM budget accounting

The Cloudflare provider distinguishes logical LLM calls from HTTP retry attempts and reports both. A provider-level logical call ceiling is enforced, with the workflow explicitly setting the same ceiling.

## Stage 5 — Citation integrity

Added `analysis/citation_validator.py`. Citation IDs are checked against known evidence source IDs and paragraph citation coverage is reported. Convergence now includes citation coverage.

This is structural citation validation, not semantic claim-to-source entailment.

## Stage 6 — Convergence and persistence

Convergence now considers section stability, section completeness, reading coverage, citation coverage, eta variance, and pending adjustment state. State persistence is atomic. Evidence paths are application-rooted.

## Stage 7 — Reading-state robustness

Reading-state storage is application-rooted and atomically written.

## Stage 8 — Configuration

Ranking depth and reading/citation convergence thresholds are configurable in `config.yaml`.

## Stage 9 — Workflow safety

The scheduled GitHub Actions workflow no longer deletes `main` and force-pushes an orphan branch. It now commits generated state normally and pushes to `main`, preserving repository history.

## Verification limitation

No live Python execution or GitHub Actions run was performed from this environment. The branch was inspected through GitHub and updated coherently, but runtime syntax/import verification still needs to be performed by the repository environment.
