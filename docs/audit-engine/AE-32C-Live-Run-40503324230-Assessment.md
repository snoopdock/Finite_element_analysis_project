# AE-32C E.5 live-run assessment — 40503324230

**Assessment status:** Operational evidence reviewed; diagnostic correctness not assessed.  
**Prepared from:** supplied G9.42 evidence and round-robin artifact archives.  
**Do not overwrite the original artifacts.**

## 1. Provenance

| Field | Value |
|---|---|
| G9.42 validation run | `40502970945`, attempt 1 |
| Validated development commit | `7c1e179a50583195fa464f97f7bd31a00c82032b` |
| Validation engine / workflow commit | `209916691f47646b86be304ce96b143b35801354` |
| Validation profile | `G9.42` |
| Validation report SHA-256 | `c9cc575caf27cdd2b15452d9295655ee2cd250fcf1a7adb414e09f3ccd76dd56` |
| Validation bundle SHA-256 | `73463230605fc04e813e225b222e1d5dca6c63ae7a2cc12d2874ceb9f1f8a944` |
| Live round-robin run | `40503324230` |
| Source commit used by live run | `7c1e179a50583195fa464f97f7bd31a00c82032b` |
| Rounds / providers | 4 / Cloudflare → NaraRouter → OpenRouter |
| Pause between trials | 60 seconds; deviation from the 120-second historical-comparison setting |

The validation report recorded 232 targeted tests passed; 3,200 regression tests total with 8 skipped and no failures; and 50 validation-engine tests passed. The evidence verifier reported both independent evidence and provenance-catalog verification as passed.

All 12 trial records were present in the live archive. I checked all 24 file hashes listed by the 12 per-trial `SHA256SUMS.txt` files; every listed comparison JSON/Markdown file matched its digest.

## 2. Batch outcome

The batch summary schema was `ae32c/batch-evaluation/v3`.

| Measure | Result |
|---|---:|
| Expected / observed trials | 12 / 12 |
| Baseline completed | 8 / 12 |
| Graph protocol completed | 5 / 12 |
| Graph evidence complete | 5 / 12 |
| Overall accepted | 5 / 12 |
| Diagnostic correctness | Not assessed |

The workflow's final gate correctly failed because not all 12 trials met the overall acceptance criteria. This is a valid fail-closed result, not a validation-workflow defect.

## 3. Provider outcomes

| Provider | Baseline completed | Graph protocol | Graph evidence | Overall accepted | Dominant observed failure |
|---|---:|---:|---:|---:|---|
| Cloudflare | 4/4 | 1/4 | 1/4 | 1/4 | 3 graph runs exhausted finalization recovery |
| NaraRouter | 0/4 | 0/4 | 0/4 | 0/4 | HTTP 400 / `provider_api_error_payload` in baseline and graph conditions |
| OpenRouter | 4/4 | 4/4 | 4/4 | 4/4 | No protocol/evidence-gate failures in these four trials |

### Cloudflare

Three graph-assisted trials ended with `finalization_recovery_budget_exhausted`; one completed and passed the declared graph evidence gate. The failed trials lacked the required direct source-anchor support and had incomplete source coverage. The remaining work is to isolate finalization/action-schema failure modes using deterministic fixtures before considering prompt or budget changes.

### NaraRouter

All four baseline calls and all four graph-assisted calls failed with the safe error classification `provider_api_error_payload`; the recorded error text was `nararouter HTTP 400`. The graph condition produced its own failure record in each trial, so the artifacts do not show baseline failure suppressing graph execution. The logs do not contain enough safe response structure to distinguish endpoint/model mismatch, request-shape incompatibility, or another provider-side rejection.

Do not synthesize a completion, silently coerce an error to success, or increase investigation budgets. Follow the focused diagnostic plan in `AE-32C-NaraRouter-HTTP400-Diagnostic-Plan.md`.

### OpenRouter

All four graph-assisted trials completed and met the declared source coverage, citation-resolution, and textual-witness requirements. Their reports still explicitly say `references_resolved_not_independently_proven`; this is not evidence that their causal explanations are correct.

## 4. Interpretation limits

- E.5 operational independence and reporting can be evaluated from the retained records; this batch does not establish general provider reliability.
- The E.5 baseline is a single-response model condition, not AE-32D's deterministic condition A.
- The 60-second pause differs from the 120-second historical-comparison setting, so timing and provider comparisons should note that deviation.
- Four trials per provider are too few to support provider rankings or broad statistical claims.
- All trials require independent human review for diagnostic correctness.
- A textual witness and resolved citation are lexical/provenance checks, not proof of causal entailment.

## 5. Decision

**Do not rerun the same batch immediately.** Preserve the artifacts. First adjudicate the provider-interface fixture independently and establish the AE-32D pilot rubric. In parallel, investigate NaraRouter's repeated HTTP 400 through request/config inspection and deterministic fixtures. Only a focused minimal live compatibility check should follow, with separate manual authorization.
