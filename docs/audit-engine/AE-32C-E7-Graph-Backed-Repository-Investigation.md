# AE-32C E.7 — Graph-Backed Repository Investigation

**Status:** implementation package prepared for `stage1/section-uuids` only.

## Objective

E.7 is deliberately narrow. It tests the original AE-32C question:

> Does the LLM actually use the repository's semantic graph to navigate source relationships, or does it merely complete the investigation protocol around a shallow graph?

The increment does not attempt to build a complete Python call graph or a general semantic-entailment framework.

## Implementation

### 1. Conservative `CALLS` relationships

`audit_engine/semantic_audit/ae32b/evidence_tools.py` now adds source-grounded `CALLS` edges for statically unambiguous AST call sites.

Supported cases include:

- direct calls to functions defined in the same module;
- calls to functions/classes imported with `from ... import ...`;
- calls through imported module aliases when the target module and symbol are unambiguous;
- `self.method()` calls within a statically identified class method.

The graph records the call-site path, line, source hash, resolution kind, and a `statically_resolved` status.

The implementation intentionally does **not** resolve:

- arbitrary instance attributes;
- alias assignments and dynamic rebinding;
- reflection;
- `getattr`;
- dynamic dispatch;
- runtime behavior;
- comprehensive type inference.

Unresolved calls are retained as limitations rather than promoted to graph facts.

### 2. Graph query evidence

`graph_neighbors` and `graph_path` now expose:

- `observed_relation_types`;
- `source_paths`;
- the existing graph evidence records and source hashes.

This makes the graph-to-source chain directly observable.

### 3. LLM graph-use contract

`RepositoryInvestigator` supports an optional controlled contract:

- `require_graph_interaction=True`;
- `required_graph_target=<exact graph selector>`;
- `required_graph_relation_types=(...)`.

When enabled, a graph-assisted investigation must:

1. perform a successful `graph_neighbors` or `graph_path` query against the exact target;
2. observe at least one requested relation, unless the graph query explicitly reports no match;
3. read at least one source path surfaced by the graph query.

The resulting report contains `graph_interaction_coverage`.

This is an evaluation control, not a correctness oracle.

### 4. Read-only graph inspection helper

`tools/validate_ae32c_e7_graph.py` performs a bounded, read-only graph query against the controlled fixture and exits non-zero if the requested relation is not observed. It makes no provider calls and does not execute repository code.

### 5. Live-evaluation controls

`ae32c/live_evaluation.py` accepts:

```text
--require-graph-interaction
--required-graph-target <selector>
--required-graph-relation-type <RELATION>
```

The graph condition can therefore be run as a genuine graph-assisted condition while leaving the no-tool baseline unchanged.

## Controlled incident pilot

For the provider-interface fixture, the intended graph target is:

```text
symbol:pipeline.extractor::extract
```

A useful first query is:

```text
graph_neighbors
  node = symbol:pipeline.extractor::extract
  direction = incoming
  relation_types = [CALLS]
```

The Stage1 fixture now produces `CALLS` observations from:

- `main.main` → `pipeline.extractor.extract`;
- `tests.checks.check_extractor_contract` → `pipeline.extractor.extract`;
- `providers.factory.build_provider` → `providers.adapter.ProviderAdapter`;
- `main.main` → `providers.factory.build_provider`;
- `tests.checks.check_extractor_contract` → `providers.adapter.ProviderAdapter`.

These are static source observations. They do not establish runtime execution.

## Acceptance criteria

E.7 is considered technically complete for this package when:

- [x] the graph contains conservative source-level `CALLS` edges;
- [x] unresolved/dynamic calls are not promoted to confirmed edges;
- [x] graph query responses expose source paths and relation types;
- [x] the investigator can enforce direct graph interaction;
- [x] graph-derived source follow-through is recorded;
- [x] the live evaluator can enable the graph-use contract;
- [x] focused regression tests pass.

The following remain separate acceptance gates:

- GitHub G9.42 validation at the manually pushed commit;
- live Qwen execution;
- evidence of improved diagnostic quality versus baseline;
- independent adjudication of diagnostic correctness.

## Scope boundary

Do not expand E.7 into:

- a complete Python call-graph analyser;
- dynamic/runtime tracing;
- embeddings or vector retrieval;
- a graph database migration;
- claim-level semantic entailment;
- confidence calibration;
- broad AE-32D benchmarking.

Those belong to later work if the pilot shows that graph-assisted navigation provides measurable value.

## Validation performed on the package

The focused local test selections passed:

- `tests/semantic_audit/test_ae32b_evidence_tools.py`
- `tests/semantic_audit/test_ae32c_investigator.py` — **88 passed**
- `tests/semantic_audit/test_ae32c_patch2_graph_workflow_fidelity.py`
- `tests/semantic_audit/test_ae32c_g942_investigator_contract_regressions.py` — **23 passed**
- `tests/semantic_audit/test_ae32c_phase_e5_independence.py`
- `tests/semantic_audit/test_ae32d_live_source_contract.py` — **17 passed**

The complete `tests/semantic_audit` suite was not accepted as a result in this preparation because the local execution exceeded the available execution window and was interrupted. No claim of a full-suite pass is made.

## Research boundary

The implementation follows the limited design conclusions adopted for E.7 from repository-level code-graph/agent research: deterministic static analysis should provide conservative code relationships, while the LLM should query and interpret those relationships through bounded tools. The package does not attempt to reproduce any external research system.
