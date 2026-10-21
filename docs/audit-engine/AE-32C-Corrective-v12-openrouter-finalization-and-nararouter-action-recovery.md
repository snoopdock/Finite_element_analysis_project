# AE-32C Corrective v12 — OpenRouter Finalization and NaraRouter Action Recovery

## Evidence reviewed

The live evaluation artifacts from runs `39599502807` (OpenRouter), `39599128718` (NaraRouter), and `39598410985` (Cloudflare) share the same source and workflow revisions.

- OpenRouter completed eight evidence-tool calls but received `json_syntax_error` in rounds 8 and 9. The run used 40,067 provider-reported tokens, below the 180,000-token cap. It stopped with `invalid_model_json`.
- NaraRouter successfully executed the initial `repository_summary`, then rejected four subsequent actions with `tool_action_shape_invalid`. The report recorded the nested argument names but not the top-level action-envelope keys. The run stopped with `invalid_tool_request`.
- Cloudflare completed its investigation and resolved citations on the same source revision, so this patch leaves its provider path unchanged.

Raw malformed model output is intentionally not retained. Therefore the exact syntax defect in OpenRouter's response is not established. NaraRouter's reason code specifically means the top-level action object did not match the exact required envelope, but the previous report lacked enough key-level diagnostics to identify missing or extra envelope fields.

## Changes

### OpenRouter / finalization
- Raises the live graph-assisted model-round allowance from 9 to 10 and reserves 3 rounds for finalization (rounds 8–10).
- Keeps the existing `max_invalid_json_retries=2`: the three finalization response opportunities now permit an initial response, two bounded correction attempts, and a final valid response if the model recovers.
- During finalization, malformed-JSON feedback explicitly requires the `final` action and only top-level keys `action` and `diagnosis`; it no longer suggests a tool call during finalization.
- Records JSON parser line and column for syntax errors, without storing or echoing raw model output.

### NaraRouter / action envelope
- Reports expected, received, missing and unexpected top-level action keys for `tool_action_shape_invalid`.
- Provides explicit feedback that tool parameters belong inside `arguments` and that the top-level envelope must contain exactly `action`, `tool`, `arguments`, and `reason`.
- Replaces the echoed malformed envelope with a value-free rejection marker when the top-level action shape is invalid.
- Adds deterministic regression coverage for the shape rejection, safe feedback, recovery and raw-value non-disclosure.

### Shared configuration
- Updates the manual confirmation text and operator guide to state one baseline call plus up to ten graph-assisted model calls.
- Adds deterministic coverage proving that two JSON-recovery attempts can be followed by an accepted final diagnosis within the reserved finalization rounds.

## Safety and unchanged behavior

- Strict JSON parsing remains enabled; malformed JSON is never accepted.
- Invalid tool actions remain rejected before dispatch; no automatic schema coercion or argument rewriting is introduced.
- Evidence provenance, snapshot verification, citation resolution, token/prompt/time limits and smoke-gate requirements remain enabled.
- The successful Cloudflare structured-JSON path is unchanged.
- The total-token budget remains 180,000; only the maximum model-round allowance increases by one.

## Installation

This patch has payloads for both branches:

1. Install `STAGE1_SECTION_UUIDS/` into the root of `stage1/section-uuids`.
2. Install `MAIN_BRANCH/` into the root of `main`. Main-branch changes only update the live-evaluation consent description and operator guide to reflect the ten-call cap.

Run G9.42 Manual Validation Dispatcher first. If it passes, rerun OpenRouter and NaraRouter separately, with Cloudflare retained as the control.

## Validation status

No repository runtime, compilation, pytest suite, or live provider request was run while preparing this patch. Archive and payload hashes verify package integrity only. GitHub validation remains pending.
