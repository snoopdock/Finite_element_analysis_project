# AE-38 — Deterministic outcome classification

## Purpose

AE-38 introduces a small, deterministic classifier for the categorical primary-outcome labels already defined in `evaluation/ae32d/scoring-rubric.json`. It classifies an audit's declared categorical outcome against a supplied ground-truth label. It does not generate ground truth, judge semantic evidence, or replace independent adjudication.

## Classification contract

Inputs are the adjudicated ground-truth label, the audit outcome (`defect_detected`, `no_defect`, or `abstain`), and a Boolean provenance-validity flag.

- Confirmed defect + detected → `correct_detection`.
- Confirmed defect + no defect → `missed_defect`.
- Confirmed defect + abstention → `incorrect_abstention`.
- No defect + detected → `false_positive`.
- No defect + no defect → `correct_no_defect`.
- No defect + abstention → `incorrect_abstention`.
- Ambiguous + abstention → `correct_abstention`.
- Ambiguous + a determinate assertion → `false_positive` (the case does not support a determinate defect/no-defect claim).
- Pending adjudication, missing output, or invalid provenance → `not_scorable`.

The classifier rejects unknown labels and outcomes rather than silently mapping them. Aggregation preserves every category and reports attempted, scorable, and not-scorable counts; the rate is null when there are no scorable cases.

## Limits and gates

1. The classifier is a mechanical implementation of the rubric's outcome categories, not a semantic auditor. It cannot determine whether a finding is materially supported, correctly localized, or causally explained.
2. `provenance_valid` must be established by the caller's separate provenance checks; this function does not verify hashes, source identity, or trial artifacts.
3. Machine-verified regression fixtures remain excluded from primary scoring until ground truth is independently adjudicated and the case set, rubric, pilot plan, prompts, model configuration, budgets, graph snapshot, and scorer are frozen.
4. This change does not approve the draft rubric, start benchmark scoring, or make any existing case gold-eligible.
5. The classifier's ambiguous-case policy is conservative: a determinate assertion on an adjudicated ambiguous case is counted as a false positive, not as a correct outcome.

## Validation

The AE-32D workflow runs dedicated unit tests for the classifier alongside benchmark-record validation and the fixed-fixture boundary tests. A passing test suite demonstrates implementation consistency with these categorical rules only; it does not demonstrate audit-engine accuracy.
