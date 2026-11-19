# AE-32C E.7.5 — Blinded Paired-Diagnosis Review Rubric

## Purpose

E.7.5 operationalizes the independent-review exit criterion for E.7. It creates two anonymized diagnosis cases from one completed, experimentally isolated control/treatment pair. Two reviewers assess the same pair independently, without receiving the provider, model, condition labels, tool catalogs, tool names, or model confidence values.

This is a review protocol, not an automated correctness judge. It does not create ground truth and does not prove that graph assistance caused an improvement.

## Entry gate

The packet builder refuses to prepare a pair unless all of the following hold:

- Both reports completed and passed their source-snapshot checks.
- The comparison reports both conditions completed and the source snapshot stable.
- The comparison records the non-graph tool sets as equal.
- The control tool catalog contains none of the five graph-derived tools:
  `graph_neighbors`, `graph_path`, `trace_execution_context`, `find_related_tests`, `find_workflow_context`.
- The treatment catalog contains all five graph-derived tools.
- The control and treatment tool catalogs differ only by that graph-derived family.
- The control report has no graph-derived tool calls.
- The treatment report contains at least one graph-derived tool call.
- Provider/model, source revision, source manifest, graph fingerprint, problem statement, and runtime limits are consistent across the pair.

This gate is intentionally stricter than trusting the legacy `graph_tool_difference_isolated` boolean alone. Earlier pilot artifacts that exposed `trace_execution_context`, `find_related_tests`, or `find_workflow_context` to control are rejected.

## Blinding

The packet builder randomly assigns control and treatment to aliases A and B. It creates two identical reviewer packets and two independent review templates. The condition mapping is stored separately under `steward/unblinding-key.json`.

Do not send the `steward/` directory to reviewers.

Provider/model identity, condition labels, tool names, operational telemetry, and model confidence are removed from reviewer packets. Diagnosis wording or cited material can still reveal methodological clues; reviewers must disclose suspected unblinding rather than claim perfect blindness.

Reviewers receive the same frozen source revision and source-manifest digest. They inspect cited paths and line numbers directly in that revision. The packet retains evidence IDs and response digests, but does not pretend that a digest is a substitute for the underlying evidence content.

## Independent review procedure

1. A steward prepares the pair packet and retains the unblinding key.
2. Reviewer 1 receives only `reviewer-1/`; Reviewer 2 receives only `reviewer-2/`.
3. Reviewers do not communicate about labels, rationales, or preferences until both submissions are complete.
4. Each reviewer evaluates cases A and B separately, then records a pair preference.
5. Reviewers inspect exact source paths/lines at the frozen source revision. A source token or textual witness is not semantic proof.
6. Each material claim is rated `entailed`, `partially_supported`, `contradicted`, or `unverified`. A contradicted claim must cite a counterevidence ID.
7. For every claim, record a verification level (`textual_witness`, `static_review`, `test_reproduction`, `independent_expert_review`, or `unverified`). Causal and runtime claims must not be rated as entailed from static source text alone; require `test_reproduction` or `independent_expert_review`.
8. Reviewers complete the blindness attestation truthfully and include a concise rationale for every case and claim.
9. The steward validates both forms, calculates descriptive agreement, preserves original forms, then reveals the A/B mapping.
10. A separate human adjudicator records any final resolution. Agreement statistics do not automatically create a gold label.

## Review dimensions

For each anonymized case:

- `overall_outcome`: correct detection, missed defect, false positive, correct no-defect, correct abstention, incorrect abstention, or not scorable.
- `localization`: exact, partial, incorrect, unsupported, or not applicable.
- `causal_explanation`: supported, partially supported, unsupported, contradicted, or unverified.
- `claim_level_support`: directly supported, indirectly supported, counterevidence present, unsupported, or not assessed.
- `evidence_integrity`: valid, incomplete, invalid, or not assessed.
- `uncertainty`: appropriate, overconfident, unnecessary abstention, or appropriate abstention.
- `actionability`: actionable, partially actionable, or not actionable.

No weighted composite score is calculated. Report each dimension and raw denominator separately.

## Agreement analysis

The agreement command reports:

- Case-level outcome agreement for A and B.
- Claim-level raw agreement.
- A claim-level confusion matrix.
- Cohen's kappa where mathematically defined.
- Claim-level disagreements requiring adjudication.
- Agreement on pair preference.

Interpret kappa cautiously: one pair and a small number of claims are not enough to establish stable reviewer reliability. If expected disagreement is zero, kappa is undefined and must remain null. Do not substitute 1.0.

## Unblinding and final status

After both records validate, the steward may run the unblind command. The result maps A/B to control/graph treatment but retains:

- `final_adjudication: pending_human_adjudicator`
- `primary_benchmark_eligible: false`

A separate adjudicator must resolve disagreements, document the evidence basis, and decide whether the case is eligible for any future benchmark. Pending or disputed cases remain excluded from primary accuracy claims.

## Scope boundary

E.7.5 does not change the investigator, graph engine, provider adapters, model budgets, or live workflows. It adds a deterministic offline review protocol. E.8 reliability and reproducibility remains a separate phase.
