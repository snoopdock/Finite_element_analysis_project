# Sequential Architecture Update Report

This branch contains the requested sequential architecture updates. The `tests/`, `formal/`, Lean, README, and wiki areas were intentionally excluded.

## Stage 1 — Stable section identity

Implemented UUID-based identity for document sections. State schema is v4. Existing valid IDs are preserved; missing, invalid, or duplicate IDs are repaired. Split children receive new UUIDs and `parent_section_ids`; merged sections receive new UUIDs with both parent IDs. Legacy title-keyed iteration history is migrated where UUIDs can be resolved.

## Stage 2 — OAA and writer identity integration

`WritingIndicator`, `DynamicWriter`, and OAA now prefer stable section UUIDs for history and structural operations. Rewrites preserve IDs. OAA actions carry `section_ids`. Split/merge/deduplicate/expansion actions operate on section identity, and merges preserve document order.

## Stage 3 — Evidence provenance and ranking

Added `research/ranking.py`. Retrieval records the exact provider and originating query for each source. Multi-query retrieval is ranked deterministically before truncation. Source quality, lexical relevance, section relevance, and citation support are surfaced as ranking components. The writer consumes ranked knowledge items.

The ranking is deterministic lexical/source-quality ranking; it is not embedding-based semantic retrieval.

## Stage 4 — LLM budget accounting

The Cloudflare provider now distinguishes logical LLM calls from HTTP retry attempts and reports both. A provider-level logical-call ceiling is enforced, and the GitHub workflow sets the configured ceiling explicitly.

## Stage 5 — Citation integrity

Added `analysis/citation_validator.py`. Citation IDs are checked against known source IDs, paragraph citation coverage is measured, and invalid references are reported. Citation coverage is included in convergence diagnostics.

This is structural citation validation, not semantic claim-to-source entailment.

## Stage 6 — Convergence and persistent state

Convergence now incorporates eta variance, audit stability, section completeness, reading coverage, citation coverage, and pending actions. State persistence is atomic. Evidence paths are application-rooted.

## Stage 7 — Reading-state robustness

Reading-state storage is application-rooted and written atomically.

## Stage 8 — Configuration

Ranking depth and reading/citation convergence thresholds are configurable in `config.yaml`.

## Stage 9 — Workflow safety

The scheduled workflow no longer deletes `main` and force-pushes an orphan branch. It now commits generated state normally and pushes the resulting commit to `main`, preserving repository history.

## Verification status

The branch was reviewed through the GitHub integration. A live Python compile/import run and a live GitHub Actions run were not performed from this environment, so runtime verification remains outstanding.
