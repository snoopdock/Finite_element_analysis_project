# AE-32C E.7-R.3N.6.1 — Context Tools and Finalization Budget

**Status:** Corrective implementation prepared for Stage1 GitHub validation
**Predecessor:** E.7-R.3N.6
**Target branch:** `stage1/section-uuids`
**Validation profile:** G9.42
**Read-only boundary:** Preserved

## 1. Purpose

E.7-R.3N.6 introduced investigation-context completeness reporting, but the investigator prompt and coverage logic referenced `trace_execution_context` and `discover_case_context` before those tools existed in the AE-32B registry and dispatch map. The same validation run exposed inherited finalization-context failures caused by character-only compaction that did not account for the provider request's estimated prompt-token reservation.

E.7-R.3N.6.1 aligns the tool contract, makes completeness fail closed on incomplete discovery, and applies the same serialized provider-request accounting to finalization compaction and provider admission.

## 2. Added AE-32B tools

### `trace_execution_context`

The tool returns bounded static observations for:

- incoming Python import relationships and caller paths;
- outgoing import relationships and dependency paths;
- Python entrypoints identified from `__main__.py` package layout or an AST `if __name__ == "__main__"` guard;
- direct import context of relevant Python entrypoints, separately labelled from direct callers;
- active CI workflow candidates returned by the existing workflow-context analysis.

The result includes `coverage_status`, `truncated`, source hashes where available, and limitations. It does not execute code and does not claim that a workflow or entrypoint ran.

### `discover_case_context`

The tool discovers bounded README, fixture-description, incident, case, scenario, and metadata candidates from the already indexed non-sensitive source set. It returns repository-relative paths, categories, source hashes, and line-numbered previews. A preview counts as complete only when all indexed lines are present, the preview is line-numbered, and the source hash is supplied. Larger previews are explicitly marked incomplete and require `read_source_file`.

Both tools are registered in `build_tool_definitions()` and `RepositoryEvidenceTools._handlers`. Existing schema validation, safe response envelopes, redaction, and response-size controls remain in force.

## 3. Static pytest classification

`find_related_tests` now adds `pytest_static_assessment` for every returned Python candidate. It reads visible `python_files` configuration from supported `pyproject.toml`, `pytest.ini`, `tox.ini`, and `setup.cfg` forms, or uses pytest's default filename patterns when no visible override exists.

The assessment uses filename matching and AST parsing only. It does not import test modules, invoke pytest, or assert that a candidate was collected or executed. Ambiguous, malformed, or unsupported configuration yields `unknown` rather than a guessed classification.

## 4. Investigation completeness schema v3

`ae32c/investigation-context-coverage/v3` requires all three discovery tools to return:

- a successful tool invocation;
- the expected list-valued result fields;
- `coverage_status: "complete_for_query"`;
- `truncated: false`.

Missing, failed, malformed, or truncated discovery keeps the overall status at `partial_discovery`.

The candidate/read/unread union includes caller, dependency, Python entrypoint, entrypoint-context, active CI workflow, related-test, and case-metadata paths. A successful `read_source_file` counts only when its exact path has a complete source range, no omitted content, and a source hash consistent with the indexed snapshot. A metadata preview counts only when it is complete, line-numbered, redaction-marked, and hash-bound.

Per-category counts are role-based and may overlap when one path serves more than one role (for example, a test file can also be a static importer). Aggregate candidate/read/unread totals are computed from the unique path union.

Overall states:

| State | Meaning |
|---|---|
| `partial_discovery` | At least one required discovery operation is absent, failed, malformed, or truncated |
| `partial_unread_candidates` | All required discovery operations completed, but one or more surfaced paths remain unread |
| `complete_for_available_static_context` | All required discovery operations completed and all surfaced candidates were inspected |

The last state is relative to the available indexed static context. It is not proof of exhaustive semantic discovery, test execution, runtime behaviour, or diagnostic correctness.

## 5. Finalization budget accounting

Finalization compaction now measures the exact provider request representation, including response-mode instructions and structured-response definitions. For each compacted variant it calculates:

- cumulative remaining prompt characters;
- remaining token reservation;
- response-token reservation for the current call;
- protected token capacity for later reserved finalization rounds.

The evidence-gathering phase cannot consume the configured finalization reserve when the total budget can support that reserve. Each finalization request preserves capacity for later reserved rounds. Plain-text fallback reservation applies the same holdback.

Compaction selects only a variant that fits both cumulative ceilings. If no evidence-preserving variant fits, it stops before a provider request with `finalization_context_budget_unavailable` and records bounded size/reservation diagnostics. Evidence IDs and bounded exact source-reference candidates are not silently dropped to force a call.

The configured per-round protected prompt reserve is 1,024 estimated tokens, in addition to the configured response-token reservation. Very small total budgets that cannot support a meaningful protected reserve retain the ordinary hard reservation check.

## 6. Tests and observed build checks

The implementation adds tests to the existing G9.42 target files and extends the finalization regression module.

Recorded checks in the package-build environment:

- Python compilation of the changed implementation and test modules: passed.
- Focused AE-32B/AE-32C evidence, investigator, controlled-incident, and finalization tests: 115 passed.
- G9.42 target selection: 29 files, 369 passed.
- Full repository test collection: 3,370 tests collected.
- Full repository execution: not completed in the package-build environment; the command exceeded the available five-minute execution window before producing a summary.

These are package-build checks, not GitHub acceptance. G9.42 must be run by the repository's Manual Validation Dispatcher against the exact committed Stage1 SHA. Full regression must complete successfully in that run.

## 7. Change boundaries

- Stage1 only: `stage1/section-uuids`.
- No `main` changes.
- No provider adapter, Cloudflare transport, response normalizer, streaming, or live-provider changes.
- No G9.42 profile or Manual Validation Dispatcher workflow changes.
- No repository code or tests are executed by the investigation tools themselves.

## 8. Acceptance sequence

1. Confirm the target branch still descends from the source snapshot used to prepare the package.
2. Apply the complete replacement files and add this document on Stage1 only.
3. Commit the changes to `stage1/section-uuids`.
4. Run the Manual Validation Dispatcher with G9.42 in `profile` mode.
5. Verify exact source SHA, validation-engine SHA, targeted test count, full regression, evidence receipt, digest, and catalog outcome.
6. Only after G9.42 passes, repeat the controlled Qwen investigation. Keep diagnostic correctness subject to independent review.

A failed validation remains failed and its evidence must be retained. No live-provider evaluation is authorized by this package alone.
