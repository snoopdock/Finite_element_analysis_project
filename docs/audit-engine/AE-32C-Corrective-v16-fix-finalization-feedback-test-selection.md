# AE-32C Corrective v16 — Fix Finalization Feedback Test Selection

## Evidence reviewed

G9.42 manual-validation run `39628117769` failed one unique test, which appeared in both the targeted and full regression suites:

`tests/semantic_audit/test_ae32c_investigator.py::test_unsupported_action_during_finalization_only_allows_final_recovery`

The failure was a `KeyError: 'validation_feedback'` at line 799. The test assumed that the last message of `provider.messages[2]` always contained the feedback object.

## Root cause

`provider.messages` stores a message history for each provider request. The feedback object is present in the conversation history, but it is not guaranteed to be the final message at one fixed request index. The assertion is coupled to incidental message ordering instead of the feedback's stable schema identifier.

## Correction

The test now searches all recorded provider request histories, safely parses JSON message content, and locates the `validation_feedback` object whose `schema_version` is `ae32c/unsupported-action-feedback/v1`.

The test continues to assert that:
- the feedback phase is `finalization`;
- the only supported action is `final`;
- the feedback explicitly prohibits further tool requests; and
- the rejected untrusted query is not echoed into the conversation.

No production code, provider configuration, transport retry, budget, workflow, validation profile, or citation rule changes.

## Installation

Install `STAGE1_SECTION_UUIDS/` into the root of `stage1/section-uuids`, preserving paths and overwriting the listed test file. Run G9.42 Manual Validation Dispatcher again.

## Validation status

No repository runtime, compilation, or tests were run while preparing v16. ZIP and payload checksums verify package integrity only; GitHub validation remains pending.
