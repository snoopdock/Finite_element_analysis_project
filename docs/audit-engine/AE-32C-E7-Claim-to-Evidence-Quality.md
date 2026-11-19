# AE-32C E.7 — Claim-to-Evidence Quality (bounded first implementation)

## Objective

Move from syntactic citation/witness checks toward a traceable, claim-level account of what evidence was actually observed, while keeping semantic entailment and causal correctness outside the automated trust boundary until measured.

## Implementation

1. `claim_evidence.py` derives stable claim IDs and deterministic evidence-linkage metadata from accepted diagnosis claims and the successful evidence ledger.
2. Every root-cause assessment and material claim records a normalized E.7 claim type, cited evidence IDs, exact source ranges/hashes, evidence linkage (`direct_source_line`, `indirect_tool_context`, `mixed_direct_and_indirect`, or `none`), and a conservative verification level.
3. A source read that is named only by evidence ID but lacks an exact source-line citation is exposed as `citation_gap`, with ledger-observed source candidates for reviewer inspection.
4. Automated `support_outcome` remains `unverified`. The code never upgrades a claim to `entailed` based on token presence, a graph edge, model confidence, or citation existence.
5. Counterevidence and unresolved assumptions are explicitly marked `not_assessed` / `not_collected`, rather than being represented as absent.
6. The report writer emits a separate `.adjudication-template.json` beside JSON and Markdown reports when an accepted diagnosis exists.
7. Two independent reviewer records can be validated and compared using raw agreement and Cohen's kappa.

## Claim taxonomy

- `observation`
- `static_inference`
- `runtime_claim`
- `causal_hypothesis`
- `recommendation`

Legacy `hypothesis` and `conclusion` values remain accepted and normalize to `causal_hypothesis` and `static_inference` respectively. `limitation` is retained as a legacy kind and treated as an observation about evidence boundaries.

## Trust boundary

The automated assessment verifies ledger linkage and exact source-range identity. It does not perform semantic entailment. A source-line citation establishes that the line was observed; it does not prove the claim, causal interpretation, or runtime behavior. Human adjudication or deterministic reproduction is required for stronger outcomes.

The independent adjudication record is separate from model output. It records supporting evidence, counterevidence, assumptions, outcome, rationale, reviewer identity, and verification level. The validation utility requires ledger-bound evidence IDs and requires test reproduction or independent expert review before a causal/runtime claim can be marked `entailed`.

## Provider independence

No provider adapter, provider credential, model profile, or live-run budget is changed. The new assessment runs after an accepted diagnosis and is deterministic. It can be exercised entirely with fixtures and later used with Cloudflare/Qwen, OpenRouter/Nemotron, or another compatible provider.

## Workflow integration

The existing main-branch matched-pilot workflow uploads the run directory recursively. The adjudication template is emitted into that same run directory by the existing report writer; no `main` workflow change is required for this increment.

## Acceptance boundary

- Deterministic linkage and source-range checks pass targeted tests.
- Adversarial token-only examples remain `unverified`.
- Reviewer records are validated against report claim IDs and ledger evidence IDs.
- Inter-rater agreement is computed only from two complete valid reviewer records.
- Semantic support outcomes remain human-assigned; automated semantic evaluation remains advisory/not performed.
- Fresh GitHub G9.42 validation is required before the later workflow/live evaluation gate.
