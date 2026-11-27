# AE-43 — Exploratory A/B/C trial integration readiness

**Status:** readiness audit complete; integration execution is gated on qualifying trial artifacts.  
**Branch:** `stage1/section-uuids`  
**Depends on:** AE-42 validated exploratory registry/scorer.

## 1. Decision

AE-43 is the correct next workstream after AE-42, but the repository does not currently contain a qualifying AE-32D A/B/C trial set. Therefore, do not fabricate trial outputs, infer diagnostic outcomes from protocol completion, or report a condition score yet.

The AE-42 trial schema and scorer provide the receiving contract. AE-43 must establish a provenance-preserving path from actual A/B/C condition executions to that contract.

## 2. Existing evidence examined

### AE-32D protocol

The benchmark protocol defines:
- A: deterministic audit baseline plus standard source search;
- B: A plus graph retrieval;
- C: B plus bounded LLM investigation;
- D: optional claim-level assessment, only after separately validated.

All conditions must use the same pinned case snapshot and declared scoring policy. Failures, abstentions, and missing outputs must be retained.

### AE-32C batch evaluation

`audit_engine/semantic_audit/ae32c/batch_evaluation.py` is an offline assessor of AE-32C provider trials. It derives protocol completion, evidence coverage, source-snapshot status, tool use and operational metrics from paired baseline/graph-assisted provider comparisons. Its returned records explicitly set `diagnostic_accuracy=not_assessed`.

It is useful operational evidence, but it is not an AE-32D A/B/C diagnostic-outcome record:
- its treatment structure is not the full A/B/C protocol;
- its provider baseline is not condition A's deterministic audit baseline;
- protocol/evidence completion does not establish defect-detection correctness;
- its output does not carry an independently adjudicated or AE-42 machine-reference outcome.

Do not mechanically convert its `passed`, `protocol_complete` or `graph_evidence_complete` fields into `defect` or `no_defect`.

### FEA provider benchmark workflow

`.github/workflows/FEA-llm-provider-benchmark.yml` is a separate, manually authorized full-pipeline provider benchmark. It compares provider runs of the FEA document-generation pipeline, not the six AE-32D repository-audit cases. Its provider matrix also differs from the active AE-32C provider decision. Those artifacts are not eligible AE-32D trial records.

### Tracked AE-32D inventory

The tracked `evaluation/ae32d` tree contains the six cases, schemas, manifest, pilot plan, scoring rubric, adjudication templates, machine-verification ledger, AE-42 machine-reference registry and exploratory-trial schema. It contains no actual A/B/C trial-output dataset or immutable raw trial bundle.

## 3. AE-43 input requirements

Before ingestion, each raw trial must establish:

1. Exact AE-32D case ID and exact source commit matching the machine-reference registry.
2. Exact condition identity: `A_deterministic`, `B_graph`, or `C_graph_llm`.
3. A common task statement and audit scope across the paired conditions.
4. Immutable run ID, workflow/run URL where applicable, tool/rule configuration digest, and source snapshot identity.
5. Raw output artifact reference and content digest; retain failed output and diagnostics.
6. A normalized outcome from an explicit, deterministic extraction/encoding step. Do not infer it from exit status, protocol completion, evidence coverage or model confidence.
7. Explicit `abstain`, `error`, and missing states. No dropping failed or inconvenient trials.
8. For C, provider/model identifier, prompt/template revision, tool catalog revision, budgets and invocation provenance.
9. For B and C, graph snapshot identity and retrieval configuration; B and C must not silently differ in unrelated settings.
10. A configuration freeze for each paired comparison. If configurations differ, mark the comparison non-comparable rather than normalize away the difference.

A machine-reference outcome is only the exploratory comparator. It must not be written back into the case record's gold label.

## 4. Execution policy

Do not automatically invoke live providers as part of a push-triggered workflow. Live provider runs require an explicit manual authorization path and must preserve the project's provider restrictions, budget ceilings and secrets boundary.

The first AE-43 implementation should be an offline artifact importer/normalizer with:
- allowlisted input roots and filenames;
- symlink/path traversal rejection;
- SHA-256 verification of raw artifacts;
- strict schema validation;
- exact case/source/condition binding;
- duplicate and cross-condition mismatch rejection;
- immutable raw input retention;
- explicit normalization provenance;
- no credential access and no provider dispatch.

A later, separate manually dispatched execution workflow may produce A/B/C trial artifacts once its budget, provider, source and configuration controls are approved.

## 5. Acceptance gates

AE-43 integration can be validated only when:
- real retained or explicitly generated A/B/C outputs exist for the same pinned case set;
- each imported trial binds to exact source/configuration identity;
- importer tests reject forged, incomplete, mismatched, duplicate and unsafe-path artifacts;
- normalized records validate against `exploratory-trials.schema.json`;
- missing/failed/abstaining trials remain represented;
- AE-42 scorer emits exploratory-only metrics without modifying any case or gold label;
- no A/B/C results are described as primary benchmark results.

## 6. Current disposition

**AE-43 is not yet implemented or validated.** The readiness audit is complete and the data prerequisite is unmet. The next safe action is to design the offline importer against actual raw artifact formats only after selecting a real, eligible A/B/C evidence bundle. If no such bundle exists, explicitly generate a controlled A/B/C set under a separately authorized manual workflow; do not substitute AE-32C protocol summaries or FEA provider benchmark outputs.
