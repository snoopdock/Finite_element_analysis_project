# AE-32C E.7.2.1 — Finalization Context Budget Correction

## Summary

This corrective increment fixes a deterministic finalization-context regression found in the Stage1 G9.42 validation run 44289046846.

The affected test is:

`tests/semantic_audit/test_ae32c_finalization_context_compaction.py::test_recovery_feedback_is_compacted_before_exact_source_candidates_are_dropped`

The failed run stopped with:

`finalization_context_budget_unavailable`

The investigator returned no diagnosis after an intentionally malformed finalization response, even though the next provider response in the fixture was valid.

## Root cause

`_finalization_context_messages()` unconditionally inserted the complete `graph_interaction_coverage` object into the model-facing finalization payload.

For investigations where `require_graph_interaction` is false, this object is not actionable model context: the coverage helper returns a large `not_required` structure with empty graph query, path, evidence, and observation collections.

The extra payload consumed the remaining cumulative prompt-character allowance. In the reproduced fixture, the smallest evidence-preserving retry prompt was 9,007 characters while only 8,906 characters remained. The 101-character shortfall caused `_compact_finalization_context()` to stop before the valid recovery response could be requested.

## Correction

The graph coverage object is now included in the model-facing finalization context only when graph interaction is required. In that case, the existing graph investigation contract and coverage remain present.

The final report's graph-interaction coverage is unchanged; this correction only avoids duplicating unused graph metadata into ordinary model context.

The budget-unavailable event now records:
- `prompt_char_budget_shortfall`
- `prompt_token_budget_shortfall`
- `graph_interaction_coverage_included`

The successful compaction event also records whether graph coverage was included.

## Regression protection

The existing finalization compaction regression now asserts that graph coverage is omitted from ordinary finalization context while exact source-reference candidates and validation feedback remain preserved.

A graph-pilot regression asserts that graph coverage and the graph investigation contract remain present when graph interaction is required.

The finalization-context regression test has also been added to the G9.42 `target_tests` selection so it runs before the full regression sweep.

## Validation performed on the uploaded Stage1 snapshot

- Reproduced the original failing test before the correction.
- After correction, focused finalization and graph-pilot tests: 15 passed.
- Extended investigator/finalization/graph tests: 76 passed.
- All 30 G9.42 target-test modules: 418 passed.
- Python 3.11 grammar parsing for all modified Python files: passed.
- YAML parsing of `validation/profiles/G9.42.yaml`: passed.

The available local runtime was Python 3.13.5. A Python 3.11 runtime was not available for execution; Python 3.11 compatibility was checked at the syntax/grammar level only. GitHub Actions G9.42 remains the authoritative Python 3.11 runtime validation.

## Scope boundary

This package does not modify:
- Graph construction or graph query behavior.
- E.7.2 graph-guided exploration policy.
- Nemotron or Qwen model profiles.
- Provider adapters or secrets.
- The `main` branch workflow.

Apply only to `stage1/section-uuids`.
