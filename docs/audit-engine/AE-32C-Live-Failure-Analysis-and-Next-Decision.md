# AE-32C E.5 live failure analysis and next decision

**Evidence reviewed:** G9.42 run `40502970945`; round-robin run `40503324230`; 12 retained trial records.  
**Status:** Operational causes are partially identified. Diagnostic accuracy remains unassessed.

## What the latest run proves

The G9.42 gate passed on development source commit `7c1e179a50583195fa464f97f7bd31a00c82032b`. The live batch then executed all 12 trials and preserved the records. The batch acceptance gate correctly failed at 5/12 overall accepted. This is not a test-suite failure: it is a live operational failure recorded by the experiment.

| Provider | Baseline | Graph protocol | Graph evidence | Overall accepted | Observed blocker |
|---|---:|---:|---:|---:|---|
| Cloudflare | 4/4 | 1/4 | 1/4 | 1/4 | Three finalization recoveries exhausted after invalid/unbound citations; required source reads were incomplete in those trials |
| NaraRouter | 0/4 | 0/4 | 0/4 | 0/4 | HTTP 400 on all baseline and graph calls; response body details were deliberately discarded |
| OpenRouter | 4/4 | 4/4 | 4/4 | 4/4 | No protocol/evidence-gate failure in this small batch; correctness not assessed |

The run used 60-second pauses, not the 120-second interval requested for historical comparability. Keep that deviation in all comparisons.

## Why the run is failing

### NaraRouter: compatibility is not diagnosed yet

The adapter currently persists only the HTTP status and a broad error category for non-transient HTTP failures. It does not retain the upstream free-form message, which is appropriate for privacy and safety, but it also does not retain safe structured fields such as error `type`, `code`, and `param`. Thus the available artifacts cannot distinguish a rejected model ID, unsupported parameter, authentication/configuration issue, or another request-contract problem.

This patch adds allowlisted, secret-safe structural error metadata. It does **not** claim to fix NaraRouter. After this patch passes G9.42, inspect the safe diagnostic from one explicitly authorized compatibility smoke test before deciding whether endpoint, model, or request construction should change. Do not repeat the full 12-trial batch just to obtain the missing error code.

### Cloudflare: mandatory evidence competes with the model's turn budget

The graph investigator has caller-declared required source paths, but previously relied on the model to spend tool turns discovering and reading those files. The observed Cloudflare traces include a reminder that one required path remained unread, followed by finalization rejections such as `root_cause_requires_non_summary_evidence`, `source_reference_not_observed`, and `source_reference_evidence_id_unbound`. The 8B model sometimes emitted invalid JSON or an invalid action envelope as well.

This patch prefetches small, explicitly required source files into the same immutable evidence ledger before the first model turn and exposes those source-read evidence IDs/content in the initial prompt. It also canonicalizes a repeated source-reference evidence ID only when the exact path, line, and SHA-256 tuple is observed in the successful ledger and matches the indexed source manifest. It does not accept invented lines, stale hashes, unread source paths, or unsupported claims. The source witness remains a lexical check, not causal proof.

The prefetch is bounded by the existing tool-call budget and the evidence tool's single-read size limits. If a required file exceeds those limits, the report records that prefetch was skipped instead of pretending the file was completely inspected.

## What adjudication does — and does not do

Independent adjudication establishes whether the controlled incident actually represents a defect and what findings are supported by the source and reproduction evidence. A second independent reviewer and an explicit adjudicator reduce the risk that the benchmark's answer key merely repeats the investigator's assumptions. This is necessary before reporting precision, recall, localization, or causal-support scores.

Adjudication does not repair an HTTP 400, make a weak model follow the JSON protocol, or add missing source reads. Those require the operational changes above. Conversely, a green protocol gate does not establish that the diagnosis is correct. Keep these as two separate workstreams.

## Next steps after upload

1. Compare the modified files against the current branch before replacing them. The source ZIP supplied earlier is dated 24 October; the latest validated commit is `7c1e179a50583195fa464f97f7bd31a00c82032b`. Do not overwrite any intervening changes.
2. Run G9.42 against the new exact development commit. The prior run `40502970945` does not validate this patch.
3. Review the new deterministic test results, especially prefetch provenance, exact source-reference rebinding, and safe HTTP error diagnostics.
4. If G9.42 passes, run `python tools/ae32c_provider_compatibility_smoke.py --confirm-live-provider-calls --provider nararouter` from a checkout with `NARAROUTER_API_KEY` set. This makes at most one provider request and records only safe structure. Do not run another 12-trial batch yet.
5. Inspect one Cloudflare investigation using the same fixed fixture and compare source-read coverage, finalization rejection reasons, token/call budgets, and final status with the retained run `40503324230`.
6. If operational completion improves, adjudicate the fixture with two blinded reviewers before scoring correctness. Keep the E.5 single-response baseline distinct from the AE-32D deterministic baseline condition.
7. Only after those focused checks pass should a new, comparability-controlled multi-round batch be considered. Set the pause to 120 seconds explicitly.

## Stop rules

- Do not loosen the source-evidence gate to make a provider pass.
- Do not treat `references_resolved` or a textual witness as proof of causality.
- Do not tune prompts to a case until its ground truth and scoring rubric are frozen.
- Do not report a provider ranking from four trials.
- Do not treat the NaraRouter error as fixed until a new, authorized smoke test returns a valid completion envelope and its diagnostics are preserved.
