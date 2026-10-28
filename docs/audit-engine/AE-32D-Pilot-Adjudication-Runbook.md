# AE-32D pilot — ground-truth adjudication runbook

**Status:** Proposed workflow; scoring is blocked until case ground truth is independently adjudicated.  
**Benchmark:** `AE32D-AUDIT-QUALITY`, protocol design `0.1`.

## Goal

Create a small, defensible pilot that can tell whether AE-32 finds real defects, avoids false alarms, localizes defects, and supports causal explanations. The immediate task is to adjudicate the existing provider-interface candidate; it is not yet a gold case.

## Stage 1 — Freeze the candidate

Use `evaluation/ae32d/cases/AE32D-CANDIDATE-PROVIDER-INTERFACE-001.json` as the intake record.

- Case source commit recorded in the case: `afcb1cba064de6f3d680f6be3085a365c6687c7b`.
- Fixture path: `tests/semantic_audit/fixtures/ae32c_provider_interface_incident`.
- Source-manifest digest recorded in the case: `5d186a8801781c0c63ea29bc102a0c67f08bf8bd8358888cc96de381a24cb0cf`.
- Verify these identities against the original case source before reviewing; do not silently replace the case source with the newer AE-32C development commit.

The claim to adjudicate is whether the consumer-side `provider.total_calls` access and adapter-side `self.calls` counter establish a real defect under the intended interface/runtime contract. Static text alone may not establish dynamic wrappers, subclass behavior, or the actual call path.

## Stage 2 — Two independent ground-truth reviews

1. Give Reviewer 1 and Reviewer 2 the same frozen case source and the reviewer-form template.
2. Do not show either reviewer the other reviewer's label, provider identity, model outputs, or E.5 provider-level results.
3. Ask each reviewer to inspect the fixture, related tests, interface definitions, and any permitted reproduction artifacts.
4. Each reviewer records:
   - label: confirmed defect, no defect, ambiguous, or pending;
   - defect family and severity;
   - exact trigger/cause locations;
   - supporting and counterevidence;
   - reproduction/test status;
   - acceptable alternative explanations;
   - whether abstention is acceptable;
   - confidence and rationale.
5. If the reviewer cannot establish the runtime or interface relationship, `ambiguous` or `pending_adjudication` is acceptable. Do not force a positive label.

## Stage 3 — Adjudicate and decide eligibility

- Store each completed reviewer form with its SHA-256 digest.
- Compare labels only after both forms are complete.
- Record agreement or disagreement and preserve both original labels.
- Resolve disagreements using a named adjudicator and explicit evidence. If unresolved, exclude the case from the primary score.
- A case may become `primary_benchmark_eligible=true` only when the ground truth and verification method are established, the record is complete, and the adjudication decision is recorded.
- Pending/disputed cases may remain regression fixtures but cannot contribute to the primary benchmark score.

## Stage 4 — Freeze the pilot design before scoring model outputs

Use `evaluation/ae32d/scoring-rubric.json` and `pilot-plan.json` as draft proposals. The owner should approve/freeze them before any primary scoring.

The pilot target is 6–10 adjudicated cases, with multiple defect families and explicit negative/no-defect and ambiguous cases. Expand toward 30–50 only after the annotation process is reliable.

The paired benchmark conditions are:

- A — deterministic audit baseline;
- B — deterministic baseline plus graph retrieval;
- C — graph plus bounded LLM investigation;
- D — optional claim-level evidence assessment, only after separately validating that assessment.

Freeze source snapshots, graph snapshots, prompts, model/version, budgets, scorer, and rubric. Retain all failures, abstentions, and artifacts.

## Stage 5 — Review E.5 outputs without experimental conflation

The 12-trial E.5 archive can be reviewed retrospectively after ground truth is adjudicated. Keep provider/model identity hidden during review when feasible and use immutable output IDs.

**Do not treat E.5 baseline as condition A.** E.5 baseline is a single-response model condition without the evidence-tool loop; it is not the deterministic audit baseline required for the AE-32D A/B/C comparison. Report retrospective E.5 results separately from the AE-32D paired ablation.

## Stage 6 — Report results

Report raw denominators and component outcomes:

- case-level correct audit outcome categories;
- defect detection, false positives, false-clean outcomes, and appropriate abstention;
- localization;
- causal explanation support/contradiction;
- evidence integrity and claim-level support;
- reviewer agreement/disagreement;
- latency, calls, cost where available, and reviewer time.

Do not create a weighted aggregate score unless its weights and decision rules are justified and frozen in advance. A resolved citation or textual witness is not semantic proof.

## Stop conditions

Stop primary scoring if source identity is uncertain, the case label is pending/disputed, the rubric changed after outputs were seen, output/provider identity was unblinded prematurely, or trial artifacts are missing. Fix the process and preserve the original records rather than silently repairing old results.
