# AE-32C Corrective v4 — Schema Recovery, Source-Path Guidance, and Test Alignment

## Why this patch exists

The supplied live evaluation (run 39420941103) shows that the expanded token budget is no longer the blocking condition. The investigator used five model rounds and four tool calls, but ended with `invalid_tool_request`. The report shows two schema-invalid actions:
- an action whose `query`, `mode`, and `max_results` fields did not match the selected tool's schema;
- a later action whose `path` field did not match the selected tool's schema.

The model also attempted source reads using `/path/to/provider.py` and `relative/path/to/provider.py`; those returned `invalid_path` and `file_not_indexed`, and produced no source references. The previous recovery logic allowed only one schema correction for the entire investigation and did not tell the model which other registered tool best matched its supplied argument names.

The accompanying G9.42 manual validation (run 39420425773) failed two tests:
- an old expected stop reason (`diagnosis_submitted`) no longer matched the explicit coverage-aware result (`diagnosis_submitted_with_coverage_or_snapshot_limitations`);
- the controlled fixture still reserved only 8,000 total tokens, which was insufficient for its six-round fake-provider conversation.

## Changes

### 1. Better schema feedback
- Includes the rejected tool name, supplied argument names, accepted argument names, required argument names, and bounded parameter schema.
- Ranks up to three possible registered tools by matching argument names. This is guidance only: the engine never silently switches tools or rewrites the action.
- Gives explicit allowed enum values for invalid enum fields.
- Records the rejected tool name and argument keys in the report without logging raw argument values.

### 2. Bounded recovery
- Increases the investigation-wide invalid-tool recovery allowance from one to three by default, configurable from zero through five.
- Every rejected action still consumes a normal model round and token/time budgets.
- Invalid actions remain rejected before dispatch. Repeated invalid actions stop when the global retry allowance is exhausted.
- No invalid action is silently repaired or executed.

### 3. Source-path recovery
- The system prompt explicitly prohibits guessed or absolute paths and recommends `search_repository` for attribute access such as `provider.total_calls`.
- After a failed `read_source_file` call with a recognized path error, the investigator adds bounded protocol guidance explaining how to find an exact indexed path.
- The guidance may include up to eight matching indexed path candidates. It is not evidence and does not make the failed read citable.
- Source-path guidance is separately bounded to two attempts by default and remains inside the existing round, time, prompt, and tool-call limits.

### 4. Regression fixes
- Aligns the stop-reason assertion with the coverage-aware contract.
- Raises the controlled fixture's total token reservation to 32,000 while retaining a 500-token per-call response limit.
- Adds tests for wrong-tool/argument mismatch, multiple bounded schema recoveries, and failed source-path guidance.
- The repeated-invalid-action test explicitly configures one retry to preserve its original single-retry assertion.
- Adds stop-reason, budget, and error diagnostics to the controlled incident test if it fails again.

## Install

Apply the `STAGE1_SECTION_UUIDS/` payload to the root of `stage1/section-uuids`, preserving relative paths. Keep Corrective v2 and v3 installed. No `MAIN_BRANCH/` payload is included and no workflow change is required.

## Validation

No local repository runtime, compilation, tests, or live-provider request was run while preparing this patch. The uploaded logs and comparison report were inspected statically. Archive hashes verify package integrity only. Run G9.42 through the existing manual validation workflow, then rerun the separate AE-32C live evaluation from `main`.
