# AE-32C Corrective v3 — Schema-Aware Tool-Action Recovery

## Purpose

Correct the live-evaluation failure in which the model's first `search_symbols` request used an unsupported `kind` enum and the investigator terminated immediately with `invalid_tool_request`.

This patch changes only the development-branch investigator, its deterministic tests, and this document. The GitHub Actions workflow, provider credentials, evidence-tool definitions, and existing validation dispatcher remain unchanged.

## Behavior

- The investigator still validates every model action against the registered evidence-tool schema before dispatch.
- On the first invalid tool action, the investigator provides bounded, structured validation feedback and allows one correction attempt.
- Enum failures include the permitted values for the affected field, such as `search_symbols.kind`: `any`, `class`, `function`, or `async_function`.
- Missing required fields and unknown fields are identified without echoing invalid field values in the feedback.
- Unknown tool names receive the registered tool-name list.
- The rejected action is sanitized before it is added to the conversation history.
- A repeated invalid action terminates with `invalid_tool_request`; no invalid request is dispatched.
- The retry consumes a normal model round and the existing token, time, response-size, tool-call, evidence-size and snapshot budgets.
- The feedback is explicitly protocol guidance, not repository evidence. It does not create an evidence-ledger entry or justify a diagnosis.

## Configuration

`InvestigationLimits.max_invalid_tool_retries` defaults to `1` and accepts values from `0` through `3`. A value of `0` disables recovery and preserves immediate rejection. The live evaluator uses the default one-retry behavior unless its configuration explicitly overrides it.

## Regression coverage

The AE-32C investigator tests cover:
- Recovery disabled: an invalid tool remains rejected before dispatch.
- Unknown extra argument: the model receives field feedback and a corrected action can proceed.
- Invalid enum: the model receives allowed values and a corrected action can proceed.
- Repeated invalid schema: the investigator stops after the configured correction opportunity.
- The original citation, evidence, provider and snapshot safeguards remain asserted by the existing test suite.

## Validation status

No repository runtime, test suite, compilation step, or live provider request was run while preparing this patch. Archive hashes establish package integrity only. Apply this patch to `stage1/section-uuids`, then rerun the existing G9.42 manual regression and the separate live evaluation from `main`.
