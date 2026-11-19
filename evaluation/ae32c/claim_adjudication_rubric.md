# AE-32C E.7 — Independent Claim-Adjudication Rubric

## Purpose and boundary

This rubric evaluates whether each material diagnostic claim is supported by the evidence recorded in one AE-32C investigation. It is separate from the model's confidence and separate from the deterministic evidence-linkage report.

The automated `claim_evidence_assessment` checks evidence IDs, direct source-read links, exact source lines and source hashes. It does **not** decide semantic entailment. A matching token, a cited line, a graph edge, or a model confidence score is not proof of a claim.

## Claim types

- `observation`: a statement directly describing what the inspected source or recorded evidence shows.
- `static_inference`: an interpretation derived from source structure, call relationships, data flow, or static test/workflow configuration.
- `runtime_claim`: a statement about behavior actually observed during execution. It requires an execution/test artifact; static source reads cannot establish it.
- `causal_hypothesis`: a proposed explanation for a failure or behavior. It is not a verified cause without stronger independent evidence.
- `recommendation`: a proposed next action or correction, whose rationale should be traceable to the diagnosis.

Legacy model kinds are normalized: `hypothesis` to `causal_hypothesis`, `conclusion` to `static_inference`, and `limitation` to an observation about the evidence boundary.

## Support outcomes

- `entailed`: the cited evidence, read in context, is sufficient for the complete proposition, with no material unresolved contradiction.
- `partially_supported`: some meaningful part is supported, but the claim is too broad, missing a qualifier, or relies on an unverified link/assumption.
- `contradicted`: evidence directly conflicts with the proposition. Cite at least one ledger-bound counterevidence ID.
- `unverified`: the evidence is absent, indirect, ambiguous, incomplete, or insufficient to decide.

Do not use `entailed` for a causal hypothesis or runtime claim based only on textual witnesses or static review. Such claims require `test_reproduction` or `independent_expert_review` as the verification level.

## Verification levels

- `textual_witness`: the exact source line was read and hash-bound. This verifies that the line was observed, not that the claim follows from it.
- `static_review`: a reviewer inspected the relevant code context and structural relationships. This is still not runtime proof.
- `test_reproduction`: a deterministic test or runtime reproduction was executed and its artifact is available in the evidence bundle.
- `independent_expert_review`: an independent reviewer assessed the claim and documented the reasoning and evidence.
- `unverified`: none of the above is sufficient.

## Review procedure

1. Two reviewers independently inspect the same immutable JSON report, Markdown report, source snapshot identity, and evidence artifacts.
2. Reviewers must not see each other's outcome assignments before submitting their own adjudication JSON.
3. For every `claim_id`, inspect the cited evidence IDs and exact source ranges. Check the source hash against the report's source manifest.
4. Decide whether the evidence is direct or indirect. A graph edge or search snippet may guide inspection but is not a substitute for reading the cited implementation line in context.
5. Record supporting evidence IDs, counterevidence IDs, unresolved assumptions, outcome, verification level, and a concise rationale.
6. Do not infer that counterevidence is absent merely because the model did not report it. Record assumptions explicitly.
7. Validate each reviewer record against the report using `tools/ae32c_claim_adjudication.py`.
8. Compare the two completed records. Report raw agreement and Cohen's kappa, alongside the number of claims and category distribution. Do not over-interpret kappa for a very small or imbalanced set.

## Adversarial checks

Reviewers should reject token-presence-only reasoning. Examples:

- A comment mentioning `provider.total_calls` does not establish that the provider object defines that attribute.
- A string literal or test fixture containing an expected field name does not prove production initialization.
- A graph `CALLS` edge establishes a static relationship under the graph's resolution method; it does not prove the call executed.
- A test candidate or workflow reference does not establish that the test or workflow ran.
- A source line that initializes `self.calls` does not establish that a different consumer's `provider.total_calls` access is compatible.

## Required reporting language

Reports must call automated results `evidence linkage` or `textual witness`, never proof of semantic support. Until human review or deterministic reproduction is complete, the support outcome remains `unverified`. Causal accuracy is reported only when the claim has independent verification.
