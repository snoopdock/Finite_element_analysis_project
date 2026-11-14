# AE-32C E.7-R.3N.6 — Investigation Context Review and Evidence Completeness

## Purpose

This increment corrects an observability defect in `investigation_context_coverage`.
Previously, invoking the three discovery tools was sufficient to label context
coverage `complete_for_available_static_context`, even when surfaced caller,
test, or case-metadata candidates had not been read.

## Behaviour

The coverage report now distinguishes:

- `partial_discovery`: one or more required discovery tools were not completed;
- `partial_unread_candidates`: discovery completed, but one or more surfaced
  caller, related-test, or case-metadata candidates remain unread;
- `complete_for_available_static_context`: discovery completed and all surfaced
  candidates were read (or were already fully represented by an allowed metadata
  preview).

The report includes bounded candidate/read/unread counts, unread paths, and
static pytest classification counts. Evaluation summaries carry these values
into comparison artifacts.

## Safety and epistemic boundaries

- This is a reporting and evidence-quality change, not an accuracy score.
- It does not automatically reject a diagnosis or change the G9.42 acceptance gate.
- A static import/caller edge is not runtime execution proof.
- A pytest collection candidate is not proof that pytest collected or ran it.
- Historical incident metadata is not proof of current runtime behaviour.
- The investigator remains read-only; runtime reproduction remains
  `not_performed_read_only` unless an external, separately evidenced execution
  result is supplied.

## Rationale from E.7-R.3N.5 live evaluation

The completed Qwen investigation correctly resolved the historical attribute
mismatch from direct source evidence, but its context review did not read all
surfaced entry-point/factory, test-helper, and case-metadata candidates.
The prior status conflated discovery-tool invocation with actual review.
This release makes that distinction explicit without weakening citation rules.
