# AE-32C E.7-R.3N.7.1 --- Mandatory Context Discovery Verification

**Status:** Corrective implementation prepared; GitHub validation
pending\
**Target Stage1 branch:** `stage1/section-uuids`\
**Expected Stage1 base commit:**
`886db126eee12628c16f39cdf2b2ed3ff62486be`\
**Expected main workflow base commit:**
`48ac1fc798f36dc116c59c72471dfce5753656`\
**Validation prerequisite:** Manual Validation Dispatcher, G9.42,
`profile` mode

------------------------------------------------------------------------

## 1. Reason for this increment

The first live Qwen evaluation after E.7-R.3N.6.1 completed its baseline
and graph-assisted investigations, resolved its final citations, and
passed the existing smoke gate. However, the investigation-context
report remained `partial_discovery`.

The report showed: - `find_related_tests`: completed; -
`discover_case_context`: completed; - `trace_execution_context`: not
called; - `main.py`: not surfaced or read; - `providers/factory.py`: not
surfaced or read.

The controlled fixture's static graph can surface: - `main.py` as a
static caller and Python entrypoint for `pipeline/extractor.py`; -
`providers/factory.py` as entrypoint context imported by `main.py`.

The previous smoke gate checked required direct-source coverage but did
not independently require complete investigation-context coverage. This
allowed the two dimensions to be reported differently without the gate
failing.

E.7-R.3N.7.1 closes that gap for the controlled provider-interface
benchmark.

## 2. Required controlled-evaluation contract

The live evaluation workflow passes these arguments to the Stage1
evaluator:

``` text
--require-complete-investigation-context
--required-context-target pipeline/extractor.py
--required-context-path main.py
--required-context-path providers/factory.py
```

The contract requires:

1.  A successful `trace_execution_context` call that resolves to
    `pipeline/extractor.py`.
2.  A complete, non-truncated trace result.
3.  Completion of all required discovery operations:
    -   `trace_execution_context`
    -   `find_related_tests`
    -   `discover_case_context`
4.  Every surfaced caller, dependency, Python entrypoint,
    entrypoint-context, workflow, related-test, and case-metadata
    candidate must be inspected.
5.  Both required benchmark paths must be surfaced by the trace and
    completely read:
    -   `main.py`
    -   `providers/factory.py`

The target may be supplied as the repository-relative file path or its
resolved module selector, provided the evidence-tool result resolves to
the configured target path/module.

These are static evidence requirements. They do not require or imply
runtime execution.

## 3. Investigator enforcement

`RepositoryInvestigator` gains an opt-in strict context contract. The
default behaviour for other callers is unchanged.

When enabled:

-   The contract and required paths are included in the initial model
    payload.
-   A final diagnosis is rejected with
    `required_investigation_context_incomplete` while the contract is
    incomplete.
-   The rejection includes structured recovery guidance listing missing
    discovery operations and unread/not-surfaced paths.
-   A reminder is added before the reserved finalization phase when
    context remains incomplete.
-   The investigator stops before entering tool-free finalization if the
    mandatory context contract is still incomplete.
-   Required context paths are tracked separately from
    `required_source_paths`; they are not automatically root-cause
    citation requirements.

The investigator continues to preserve the read-only boundary. It does
not execute repository code, run tests, or infer runtime behavior from
static relationships.

## 4. Coverage semantics

The existing context-coverage states remain distinct:

  -----------------------------------------------------------------------------
  Status                                    Meaning
  ----------------------------------------- -----------------------------------
  `partial_discovery`                       A required discovery operation is
                                            missing, failed, malformed,
                                            truncated, or did not surface a
                                            required benchmark path

  `partial_unread_candidates`               Discovery completed, but one or
                                            more surfaced/required candidate
                                            paths remain unread

  `complete_for_available_static_context`   Required discovery completed
                                            without truncation and all
                                            surfaced/required paths were
                                            inspected
  -----------------------------------------------------------------------------

The `required_context_contract` report object records: - exact required
target; - resolved target module; - successful trace count for that
target; - each required path's `surfaced`, `read`, and `status`
values; - a separate contract status.

A required path counts as read only after a successful, complete
`read_source_file` result bound to the source snapshot hash. A search
result, graph edge, filename, or partial preview does not count as a
complete source read.

## 5. Comparison report changes

The evaluation summary and Markdown comparison now show these
independently:

-   `required_source_coverage_status`: direct reads and root-cause
    citations for caller-declared required source files;
-   `investigation_context_coverage_status`: completeness of the broader
    bounded discovery/read process;
-   `required_context_contract_status`: exact-target trace and
    required-path contract;
-   required target and resolved module;
-   required context paths and their read/surfaced statuses.

The report continues to state that diagnostic accuracy is not
automatically assessed and requires independent human review.

## 6. Live smoke-gate v2

The manual live-evaluation workflow on `main` now uses:

`ae32c/live-smoke-gate/v2`

It adds separate checks for:

1.  `investigation_context_discovery_complete`
2.  `execution_context_trace_invoked_for_required_target`
3.  `required_context_path_roles_verified`
4.  `required_entrypoint_and_factory_context_read`

The role check verifies: - `main.py` appears among static callers; -
`main.py` appears among Python entrypoints; - `providers/factory.py`
appears among entrypoint-context paths.

The gate continues to check `required_source_evidence_complete`
separately. A green smoke gate therefore requires both direct
required-source evidence and the broader context contract. It still does
not assess causal correctness.

## 7. Budget and boundedness

The controlled live evaluator's cumulative prompt-character ceiling
increases from 200,000 to 350,000 to accommodate the additional bounded
trace and source-read turns.

The existing independent limits remain in force: - maximum 10 model
rounds; - maximum 12 evidence-tool calls; - maximum 180,000 estimated
total tokens; - existing provider-specific elapsed-time limits; -
existing per-call response-token cap; - existing finalization reserve; -
existing evidence-byte and source-snapshot limits.

This does not increase the number of allowed model rounds or
evidence-tool calls.

## 8. Changed files

### Stage1 --- `stage1/section-uuids`

-   `audit_engine/semantic_audit/ae32c/investigator.py`
-   `audit_engine/semantic_audit/ae32c/live_evaluation.py`
-   `audit_engine/semantic_audit/ae32c/evaluation.py`
-   `tests/semantic_audit/test_ae32c_patch4_incident_evaluation.py`
-   `docs/audit-engine/AE-32C-E7R3N7.1-Mandatory-Context-Discovery-Verification.md`
    (new)

### Main --- live-evaluation control plane only

-   `.github/workflows/ae32c-live-evaluation.yml`
-   `tools/tests/test_ae32c_validation_gate_workflows.py`
-   `docs/audit-engine/AE-32C-live-evaluation-workflow.md`

The main-branch change is limited to the manually triggered
live-evaluation workflow, its workflow-contract test, and its operator
guide. No application code, provider adapter, response normalizer,
streaming implementation, G9.42 profile, or Manual Validation Dispatcher
implementation is changed.

## 9. Test and validation requirements

Package-build checks include:

-   focused AE-32B/AE-32C tests;
-   the exact G9.42 target-test list;
-   main-branch live-workflow contract tests;
-   YAML parsing and inline Python compilation.

GitHub remains authoritative. The exact new Stage1 commit must pass: -
G9.42 targeted tests; - full repository regression; - detached evidence
verification; - provenance catalog verification.

Only after that exact-commit validation passes should the live
Cloudflare Qwen evaluation run.

The next live evaluation must produce: - a successful
`trace_execution_context` record for `pipeline/extractor.py`; -
`main.py` and `providers/factory.py` surfaced in their expected static
roles and completely read; - all three discovery operations complete and
non-truncated; - `complete_for_available_static_context`; - a passed
smoke-gate v2; - a separate human diagnostic-accuracy review.

------------------------------------------------------------------------

## 10. Explicit exclusions

This increment does not: - modify Cloudflare or OpenRouter provider
adapters; - alter response normalization or streaming; - change the
G9.42 profile; - change the Manual Validation Dispatcher; - execute the
controlled fixture or its tests during live investigation; -
automatically mark diagnostic accuracy as passed; - modify the
repository's application code on `main`.
