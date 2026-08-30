# Sequential Architecture Update Report

This branch contains the sequential architecture updates requested for the pipeline. The `tests/`, `formal/`, Lean, README, and wiki areas were intentionally excluded.

## Stage 1 — Stable section identity — complete

Implemented UUID-based section identity and lineage. State schema is v4. Existing valid IDs are preserved; missing, invalid, or duplicate IDs are repaired. Split children receive new IDs with parent lineage. Merged sections receive new IDs with both parent IDs. Legacy title-keyed iteration history is migrated when the section UUID can be resolved.

## Stage 2 — OAA and writer identity integration — complete

`WritingIndicator`, `DynamicWriter`, and OAA now prefer section UUIDs for persistent history and structural operations. Rewrites preserve IDs. OAA actions carry `section_ids`. Split, merge, deduplicate, and expansion actions operate on stable identity. Merge operations preserve document order.

## Stage 3 — Evidence provenance and ranking — complete

Added `research/ranking.py`. Retrieval records the exact provider and originating query for every source. Multi-query retrieval is ranked deterministically before truncation. Ranking exposes lexical relevance, source-quality prior, section relevance, and citation support. The writer consumes ranked knowledge items.

The current ranker is deterministic lexical/source-quality ranking; it is not embedding-based semantic retrieval.

## Stage 4 — LLM budget accounting — complete

Cloudflare provider statistics distinguish logical calls from HTTP retry attempts. A provider-level logical-call ceiling is enforced, and the workflow supplies the configured 20-call ceiling explicitly.

## Stage 5 — Citation integrity — complete for structural validation

Added `analysis/citation_validator.py`. Citation IDs are checked against known source IDs, paragraph coverage is measured, invalid references are reported, and citation coverage participates in convergence.

This does not yet prove semantic claim-to-source entailment.

## Stage 6 — Convergence and persistence — complete

Convergence incorporates eta variance, audit stability, section completeness, reading coverage, citation coverage, and pending actions. State persistence is atomic. Evidence paths are application-rooted.

## Stage 7 — Reading-state robustness — complete

Reading-state storage is application-rooted and atomically written.

## Stage 8 — Configuration — complete

Ranking depth and reading/citation thresholds are configurable in `config.yaml`.

## Stage 9 — Workflow safety — complete

The scheduled workflow no longer deletes `main` and force-pushes an orphan branch. It now commits generated state normally and pushes it to `main`, preserving repository history.

## Verification limitation

The GitHub integration was used to inspect and modify the branch, but this environment did not execute the Python application or a GitHub Actions run. Runtime import/compile verification therefore remains outstanding.
