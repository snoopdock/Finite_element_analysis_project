# AE-32D — Audit-quality benchmark protocol (design v0.1)

**Status:** Protocol proposal and case-intake scaffold; not an approved benchmark result.  
**Purpose:** Measure whether AE-32 improves defect detection, localization, causal explanation, and review efficiency—not merely whether it completes a protocol or satisfies lexical evidence gates.

## 1. Research questions

1. Does deterministic auditing plus graph retrieval improve defect detection or localization over deterministic auditing and ordinary source search?
2. Does bounded LLM investigation add further value over the deterministic-plus-graph condition?
3. Do reports distinguish observations from hypotheses, cite evidence that supports the specific claim, acknowledge counterevidence, and abstain when evidence is insufficient?
4. Is any improvement worth its latency, provider cost, and human review burden?

The primary outcome is **independently adjudicated audit quality**. Protocol completion, source coverage, textual witnesses, citation integrity, latency, and cost are secondary operational measures.

## 2. Benchmark construction

Build a carefully adjudicated pilot of 6–10 cases before expanding toward 30–50 cases. A larger set is not useful if its labels or reproduction conditions are uncertain.

Include multiple defect families:

- real defects with confirmed fixes or reproducible failures;
- seeded interface/contract mismatches;
- missing or incorrect graph relationships;
- data-flow and control-flow defects;
- stale or inconsistent documentation;
- negative controls and no-defect cases;
- ambiguous cases where insufficient evidence or abstention is the correct outcome;
- adversarial repository content that attempts to mislead the investigator.

Keep the existing provider-interface incident as a regression/candidate case. It must not be the sole benchmark and must not enter the primary score until independent review is complete.

## 3. Case ground truth

Each case must freeze:

- repository identifier, exact commit SHA, environment, and fixture or checkout path;
- task statement and declared audit scope;
- defect status, family, severity, affected files/symbols/ranges, and expected root cause;
- supporting and counterevidence with exact evidence references;
- tests, reproduction steps, confirmed fix, or other ground-truth method;
- acceptable alternative explanations and conditions under which abstention is correct;
- annotation provenance, confidence, reviewer decisions, and adjudication record;
- whether the case is eligible for the primary benchmark or held out.

A source token, resolved citation, model assertion, or LLM judge alone is not ground truth. For real defects, prefer a confirmed fix, failing test, or independent reproduction. For seeded defects, record the seed construction and have a reviewer verify that the intended defect is actually present and detectable.

## 4. Independent review

Use two reviewers for each high-value case. Reviewers should label cases independently and, where feasible, be blind to provider and evaluation condition. Adjudicate disagreements and preserve both original labels plus the resolution. Report reviewer agreement and the disagreement categories; do not hide difficult cases by dropping them after results are seen.

A case with pending or disputed ground truth may be used for tool-development and regression testing, but it must be excluded from the primary benchmark score.

## 5. Paired ablation conditions

Run the same case snapshot and scoring policy through the following conditions:

- **A — Deterministic baseline:** existing deterministic audit and standard source search.
- **B — Baseline + graph:** A plus graph retrieval.
- **C — Graph + bounded LLM:** B plus the read-only, bounded investigation loop.
- **D — Optional claim assessment:** C plus claim-level evidence assessment, only after that assessment has been separately tested.

Freeze the model/version, prompts, budgets, tools, source commit, graph snapshot, and scoring rubric within each comparison. Use paired cases; randomize order where feasible. Repeat nondeterministic conditions when justified and retain all trials, including failures and abstentions. Do not compare results from different acceptance policies as though they were the same experiment.

## 6. Scoring rubric

Score each case independently on the dimensions below. Do not collapse them into a single “pass” without retaining the component scores.

| Dimension | Allowed outcomes |
|---|---|
| Defect detection | correct detection / missed defect / false positive / abstained / not applicable |
| Localization | exact / partial / incorrect / unsupported / not applicable |
| Causal explanation | supported / partially supported / unsupported / contradicted / unverified |
| Evidence integrity | valid / incomplete / invalid / not assessed |
| Claim-level support | directly supported / indirectly supported / counterevidence present / unsupported / not assessed |
| Uncertainty and abstention | appropriate / overconfident / unnecessary abstention / appropriate abstention |
| Actionability | actionable / partially actionable / not actionable |
| Operational burden | elapsed time, provider/model calls, token usage, cost when available, reviewer time |

A textual witness is a lexical check only. A citation resolving to a source line is not proof that the line entails a claim. Causal correctness should be reported only where a reviewer, test, or independent reproduction supports it.

## 7. Primary and secondary metrics

Pre-register one primary metric before scoring the pilot. Recommended primary report: **case-level correct audit outcome**, with separate counts for true positives, false positives, false negatives, correct no-defect outcomes, and correct abstentions. Do not use raw protocol completion as the primary metric.

Report at minimum:

- defect-level precision and recall where labels permit;
- false-positive and false-clean rates;
- localization accuracy;
- causal-explanation support rates;
- claim-level evidence-support outcomes;
- evidence completeness and citation integrity;
- abstention quality;
- median and distribution of latency, provider calls, cost when available, and human review time;
- per-defect-family outcomes, raw denominators, missing cases, and reviewer agreement.

For a small pilot, present raw counts and uncertainty plainly. Do not claim general accuracy or provider superiority from four trials per provider or from one incident.

## 8. Leakage and holdout controls

Separate development cases from a hidden holdout set by repository or defect family where possible. Do not tune prompts, witness tokens, rules, or scoring thresholds against holdout outcomes. Version and hash the case set, prompts, model configuration, scorer, and source snapshots. If labels or acceptance policy change, retain the previous version and rescore the same raw outputs where possible.

## 9. Acceptance gates

The pilot is ready for scoring only when:

- the case schema validates every case;
- each scored case has an exact source snapshot and reproducible evidence;
- ground truth is independently reviewed or explicitly excluded from the primary score;
- the rubric and primary metric are frozen before model outputs are inspected;
- A/B/C conditions use the same cases and declared comparison policy;
- every trial and artifact is retained and traceable;
- protocol success, evidence completeness, and diagnostic correctness remain separate;
- results include failures, abstentions, raw denominators, and reviewer disagreements.

Do not start provider prompt tuning or broader E.6 optimization until this pilot can distinguish a model/protocol failure from an incorrect or unsupported diagnosis. If the pilot reveals a concrete adapter defect, fix it with deterministic fixtures and preserve the prior benchmark outputs.

## 10. First implementation step

Review and adjudicate `evaluation/ae32d/cases/AE32D-CANDIDATE-PROVIDER-INTERFACE-001.json`. Add a small set of cases from distinct defect families and negative controls. Do not populate benchmark scores or label this scaffold as a completed gold set until those reviews are recorded.
