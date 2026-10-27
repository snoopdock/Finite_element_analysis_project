# AE-32C Phase E.5 — independent evaluation conditions and source witnesses

Status: E.5 reporting-contract v2 passed G9.42 run `40166491875` at source commit `afcb1cba064de6f3d680f6be3085a365c6687c7b`. The live batch `40166657083` retained and reconciled all 12 trials but failed overall operational acceptance (7/12 accepted). This follow-up introduces v3 failure attribution and benchmark protocol files; **the v3 changes are not yet validated**. Do not run another live batch until a new exact-commit G9.42 run passes.

## Evidence motivating this change

The E.4 live batch accepted 6/12 protocol completions but 0/12 evidence-complete results. Four NaraRouter baseline attempts failed before a graph-assisted investigation was started, three returning HTTP 200 envelopes without the required `choices` field. Accepted diagnoses sometimes cited the right file but not the line containing the declared interface token.

## Evaluation conditions are independent

The no-tool baseline and graph-assisted investigation share the same verified repository evidence manifest and graph fingerprint but have **separate provider instances, logical-call budgets and recorded outcomes**. A baseline timeout or malformed envelope does not stop the graph run. Changes to the common snapshot still fail closed. Repository-index initialization errors still prevent unsafe execution. Publication returns zero only after producing the comparison artifacts; whether either condition passed is established *by the offline batch gate*, not the publisher exit status.

The batch measures distinct concepts:

- `baseline_complete`: a usable baseline model answer was returned;
- `graph_protocol_complete`: the graph protocol met its independent operational constraints;
- `graph_evidence_complete`: the graph-assisted condition met declared source-file and literal line-witness requirements, independently of baseline completion;
- `overall_accepted_trials`: the count of trials where baseline, graph, evidence, and integrity gates all passed;
- `passed`: all expected trials passed the overall gate, with artifacts intact.

The v2 batch summary removed the ambiguous `evidence_complete` count and was used in live run `40166657083`. Review of that run exposed a separate naming problem: `graph_failure_classes` contained provider error codes, while the actual outcome class was available per trial and stop reasons were summarized separately. The v3 contract separates `graph_protocol_failure_classes`, `graph_evidence_failure_classes`, `graph_provider_error_codes`, and `baseline_error_codes`. Individual trial records use `ae32c/trial-gate/v3`; batch summaries use `ae32c/batch-evaluation/v3`. All aggregate counts must reconcile with per-trial records and provider aggregates.

The batch summary includes provider denominators, graph-only evidence counts, overall accepted-trial counts, stop reasons, failure classes, and provider error codes even when the baseline fails. A successful model answer is **not** an independently established accurate diagnosis.

## Structured provider-envelope telemetry

NaraRouter and OpenRouter remain constrained to standard `choices`-based OpenAI-compatible completions. The adapter now records bounded structural diagnostic categories: a valid choices list, upstream error object, alternate wrapper, unrecognized object, or non-object response; and an allowlisted choices-shape class. **Alternate wrappers are not guessed into model completions.** HTTP 200 plus an error object remains a failed provider call. No upstream error text, request or response body, credentials, model-generated content, arbitrary fields, or tokens are written into these diagnostic categories.

Graph reports and baseline comparisons expose only allowlisted error and envelope categories. These are operational diagnostics, not definitive proof of a provider defect.

## Precise source-line witness guidance

During finalization, and on applicable invalid-diagnosis feedback, the investigator offers exact `(evidence_id, path, line, source_sha256)` candidates that match declared textual anchors in *directly observed source-read evidence*. A missing candidate is marked `not_observed`; the model must acknowledge that gap rather than fabricate a line. No rule for accepting a diagnosis or counting a complete source inspection is relaxed. Exact textual matches do not prove absence of other members, runtime causality, or diagnostic accuracy.

## Workflow and safety

No push trigger, scheduled provider call, auto-edit or auto-commit is introduced. Run G9.42 validation through the manual dispatcher, then manually dispatch the existing `AE-32C Round-Robin Provider Evaluation (Manual)` from `main` with the new successful run ID and explicit provider consent. The sequence remains Cloudflare → NaraRouter → OpenRouter, repeated for each selected round, with delays and independent trial artifacts. The historical-comparison pause is 120 seconds; exploratory pauses must be labelled as deviations. The job can still fail overall even if a graph investigation succeeds after its baseline failed.

E.5 makes **no claim** of improving provider reliability until new E.5 live runs are compared against the prior E.4 evidence. NaraRouter's alternate response shape cannot be safely normalized without an independently documented response contract and dedicated tests.
