# AE-32C E.7.4 — Graph-Derived Tool Isolation

## Purpose

The previous matched pilot exposed only `graph_neighbors` and `graph_path` in the treatment, but left `trace_execution_context`, `find_related_tests`, and `find_workflow_context` available in both conditions. Those tools traverse the same SemanticGraph and therefore leaked graph-derived relationship information into the nominal control.

E.7.4 corrects the experimental intervention. The control is now source-only; the treatment receives the complete graph-derived relationship tool family.

## Graph-derived tool family

The canonical tool inventory is declared in `audit_engine/semantic_audit/ae32b/evidence_tools.py`:

- `graph_neighbors`
- `graph_path`
- `trace_execution_context`
- `find_related_tests`
- `find_workflow_context`

All five are withheld from source-only control and available to graph-assisted treatment. The non-graph tool sets must match exactly.

## Source-only control

The control retains:

- `repository_summary` (with graph-specific counts, relation summaries, call-graph statistics, and graph identity metadata removed from the model-facing view)
- `search_repository`
- `read_source_file`
- `search_symbols`
- `discover_case_context`
- `search_decision_history`

It does not receive graph-derived relationship paths, test-import relationships, workflow invocation relationships, or graph query tools. The authoritative evidence ledger and runner-side provenance continue to retain the complete graph fingerprint and repository summary for snapshot integrity; only the model-facing control view is redacted.

## Graph-assisted treatment

The treatment retains the same non-graph tools and receives all five graph-derived tools. The existing bounded `graph_neighbors` query and graph-to-source follow-through contract remain unchanged.

## Reporting changes

- Comparison schema advances to `ae32c/paired-graph-pilot/v2`.
- The comparison records the expected graph-derived tool set, actual control/treatment sets, missing treatment tools, and any leaked control tools.
- `graph_derived_tool_difference_isolated` is added; the legacy `graph_tool_difference_isolated` key is retained for existing gates.
- Source-only control coverage marks graph-derived discovery tools as `not_available_by_design`, not as failed or missing operations.
- The profile no longer instructs the control to call `trace_execution_context`.

## Validation boundary

This phase changes experiment validity, not the graph algorithm or provider adapters. It does not establish causal graph benefit. The next live pair must use the same provider/model, task, source snapshot, and budgets in both conditions. Independent adjudication remains necessary before comparing diagnostic quality.

E.8 reliability and reproducibility work remains a separate follow-on phase after the E.7 correctness and evidence gates are accepted.
