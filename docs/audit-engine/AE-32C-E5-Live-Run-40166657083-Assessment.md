# AE-32C E.5 live-run assessment — run 40166657083

**Assessment status:** Evidence reviewed; operational batch failed its declared overall gate.  
**Prepared from:** uploaded GitHub Actions logs, validation evidence, round-robin artifact, and per-trial manifests.  
**Do not interpret this report as an independent diagnosis-correctness assessment.**

## 1. Provenance

| Item | Recorded value |
|---|---|
| G9.42 validation run | `40166491875`, attempt 1 |
| Validation source branch | `stage1/section-uuids` |
| Validated source commit | `afcb1cba064de6f3d680f6be3085a365c6687c7b` |
| Validation/workflow engine commit | `8c552c4968e9ded5a89bfb406986f2d9af687882` |
| Validation profile | `G9.42` |
| Targeted tests | 231 passed |
| Full regression | 3,189 passed, 8 skipped, 148 warnings |
| Validation-engine tests | 50 passed |
| Validation bundle SHA-256 | `f219bbfe36e2a186fef913a73ab601f914657e3903cc122bed0ba9b0c4b70310` |
| Round-robin run | `40166657083`, attempt 1 |
| Batch schema | `ae32c/batch-evaluation/v2` |
| Selected rounds / pause | 4 rounds / 60 seconds |
| Expected / observed trials | 12 / 12 |

The validation report, receipt, catalog, and bundle manifest agreed on the source commit, engine commit, run ID, profile, and checksums. The regression result was 3,189 passed and 8 skipped (3,197 tests collected); the eight skips were recorded as optional/environment-dependent. The 148 warnings did not fail the declared G9.42 profile.

The round-robin workflow pinned the source checkout to the validated commit and verified the detached validation evidence before provider calls. The uploaded batch contained 12 per-trial manifests covering 24 comparison files; all listed SHA-256 values matched. Batch totals and provider subtotals reconciled with the 12 trial records.

## 2. Aggregate outcomes

| Measure | Result |
|---|---:|
| Baseline completed | 12/12 |
| Graph protocol completed | 10/12 |
| Graph evidence complete | 7/12 |
| Overall accepted trials | 7/12 |
| Diagnostic accuracy independently assessed | No |
| Human review required | Yes |

| Provider | Graph protocol | Graph evidence | Overall accepted | Median elapsed seconds |
|---|---:|---:|---:|---:|
| Cloudflare | 3/4 | 0/4 | 0/4 | 13.108 |
| NaraRouter | 3/4 | 3/4 | 3/4 | 253.755 |
| OpenRouter | 4/4 | 4/4 | 4/4 | 7.442 |

The workflow's final nonzero exit was expected under its fail-closed policy: five trials did not meet all required acceptance gates. The evidence artifacts were uploaded despite that failure. Do not change the gate to make this batch green.

## 3. Observed failure classes

The v3 assessor was also run **offline** against the preserved v2 comparison artifacts. This was a re-score of existing evidence, not a new provider run. It reproduced the same denominators and pass counts while making the categories explicit: `graph_protocol_failure_classes = {model_protocol_or_budget: 2}` and `graph_evidence_failure_classes = {source_or_evidence: 3}`. The two protocol failures still have `unclassified_or_none` provider error codes; those codes are now kept separate from the observed outcome classes.

### Cloudflare

- Three graph investigations completed the protocol but failed the evidence gate because the required direct-cited `self.calls` anchor in `providers/adapter.py` was missing.
- The reports had source reads for both required paths in those three trials, but only the caller-side `provider.total_calls` witness was directly cited. Source coverage did not imply source-witness completeness.
- The fourth graph investigation stopped with `finalization_recovery_budget_exhausted`; both required root-cause citations were absent and the adapter source read was missing.
- The logs include rejected tool actions missing the required top-level `reason` field. This is a model/action-schema issue in the observed trial, not evidence of a transport failure.

### NaraRouter

- Three graph investigations passed the declared evidence gate.
- The fourth stopped with `invalid_model_json` after a long run (about 299 seconds). Source reads were complete, but the final diagnosis/citations were not accepted.
- The run recorded that structured JSON mode was not requested because the adapter capability was unavailable or unverified. Do not enable JSON mode until the provider/model contract is established and tested.

### OpenRouter

- All four trials passed the declared protocol and source-evidence gates.
- This is a four-trial operational result, not a provider ranking and not evidence of causal correctness.

## 4. Experimental deviation

The workflow was dispatched with a **60-second pause**, while the handoff protocol specifies **120 seconds** for historical comparability with E.4. The results are valid as an observed bounded batch, but the timing setup is a recorded protocol deviation. The workflow default should be 120 seconds for future historical-comparison runs; shorter pauses should be explicitly treated as exploratory.

## 5. What E.5 established — and did not establish

**Established by this run and its artifacts:**

- all 12 trials were represented and their artifacts retained;
- baseline and graph outcomes were recorded separately;
- the graph condition was not suppressed by baseline failure in the implementation's deterministic regression test;
- graph evidence completeness and overall acceptance were distinct and reconciled;
- missing textual witnesses remained evidence-incomplete;
- the final batch gate failed closed when any required trial failed.

**Not established:**

- live behavior when the baseline itself fails, because all 12 baselines completed in this batch (the condition-independence property is covered by an offline test);
- general provider reliability or statistical superiority;
- that any of the 12 diagnoses is causally correct;
- that textual witness presence proves the complete diagnosis;
- that 60-second and 120-second pause runs are directly comparable.

## 6. Decision

Treat E.5's **measurement-correctness objective as provisionally met**, subject to the reporting-taxonomy correction in the accompanying v3 files and a new exact-commit G9.42 run. Treat this live batch as **operationally unsuccessful**, not as a failed validation run.

Do not increase retry budgets or weaken witness requirements. The next project-level priority is an independently adjudicated audit-quality benchmark. Provider/prompt tuning should be conditional on reproducible failure classification and benchmark evidence.

Before another live batch, upload the v3 reporting files, run G9.42 against the new development commit, and use the successful run ID. The 40166657083 artifacts remain immutable historical evidence and should not be overwritten.
