# AE-32C E.8.4 — Graph-based impact and dependency analysis

**Status:** rebased implementation prepared; upload only after E.8.3.1 passes GitHub G9.42  
**Baseline:** E.8.3.1 corrected all-backend query integration package  
**Scope:** `stage1/section-uuids` only

## Objective

Expose direct/transitive dependency analysis and bounded reverse-impact analysis to the LLM through the existing graph-derived evidence-tool family, without increasing the number of registered tools or weakening prompt/token limits.

## LLM-facing interface

The existing `graph_neighbors` tool gains three additional `direction` modes:

| `direction` value | Behavior |
|---|---|
| `outgoing` | Existing outgoing neighborhood traversal |
| `incoming` | Existing incoming neighborhood traversal |
| `both` | Existing bidirectional neighborhood traversal |
| `dependencies` | Direct and transitive outgoing `IMPORTS` / `DEPENDS_ON` relationships |
| `dependents` | Direct and transitive incoming `IMPORTS` / `DEPENDS_ON` relationships |
| `impact` | Ownership resolution followed by bounded reverse dependency propagation |

This keeps the registered tool family stable and avoids adding two more tool schemas to every LLM request. The model does not receive separate `graph_dependencies` or `graph_impact` tools.

## Impact algorithm

For a changed file, module or symbol:

1. Resolve immediate ownership peers using `IMPLEMENTS`, `IMPLEMENTED_BY`, `DEFINES` and `MEMBER_OF`.
2. From the changed entity and its ownership peers, traverse incoming dependency relations.
3. Default impact relations are `IMPORTS`, `DEPENDS_ON`, `CALLS`, `INVOKES` and `TESTS`.
4. Deduplicate candidates deterministically and retain the shortest discovered path, relation types and evidence IDs.
5. Report direct and transitive candidates, related tests, workflow candidates, evidence, source paths, traversal bounds and truncation state.

All traversals use the selected E.8.3 backend and its per-query parity check against the Python reference.

## Evidence semantics

Impact is a structural candidate report, not a prediction of severity or proof of runtime behavior.

- `IMPORTS` is a static AST import observation.
- `CALLS` is a conservative statically resolved AST call observation.
- `INVOKES` is a static workflow command observation.
- `TESTS` is a static import relationship.
- None of these proves that a workflow, function or test executed.
- No automatic correctness score, severity rating or repair approval is generated.

Each result preserves source edge evidence, line/path metadata where available, source hashes, and explicit bounds. If the ownership or dependency traversal is truncated, the analysis status is `incomplete` and `coverage_status` is `partial`; the tool does not label partial results complete.

## Dependency analysis

The dependencies mode reports direct and transitive dependencies. Dependents mode reverses the direction and reports consumers. The tool includes the selected relation vocabulary, depth and result-limit truncation state.

The existing `DependencyAnalyzer` remains the underlying dependency query primitive; E.8.4 adds direct/transitive counts and the LLM-facing grouping.

## Relationship to future deterministic actions

E.8.4 is read-only. It does not generate or execute patches. Its evidence-backed impact candidates are intended to become inputs to a later deterministic action planner, which must independently enforce permissions, preconditions, postconditions, idempotency and execution receipts.

## Validation

Tests cover file/module/symbol ownership resolution, direct and transitive impact, tests/workflow candidates, truncation, multiple-source rejection, dependency grouping, source-path evidence and parity under NetworkX and SciPy. GitHub G9.42 validation against the E.8.4 commit remains the acceptance gate.


## Corrective-parent rebasing note

This E.8.4 package is rebased on AE-32C E.8.3.1, which repairs G6.1/G6.2 compatibility with the richer SciPy side-channel schema. The merged G9.42 profile retains the G6.1 and G6.2 benchmark suites in its targeted selection and adds the E.8.4 impact-analysis suites. Do not install this package on the failed E.8.3 branch. First upload and validate E.8.3.1, then compare the E.8.4 baseline hashes against the accepted E.8.3.1 branch.
