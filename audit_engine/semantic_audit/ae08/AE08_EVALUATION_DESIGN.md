# AE-08 Evaluation Design and Claim Calibration

**Research question:** On an explicitly labeled, exact-byte bounded Python source corpus, does the Audit Engine reproduce source import relationships, resolution uncertainty, and confirmed architectural policy violations correctly? **Separate question:** What descriptive source scope exists in the unlabeled repository snapshot?

**Unit of observation:** One import occurrence with file, line, column, import syntax/form, module/symbol, alias, execution context, certainty status, and resolved target. For findings, one source-location+target tuple with verified G3 evidence.

**Reference oracle:** Manually entered JSON labels, source SHA-256 per file, all fixture `.py` paths, human rationale. The reference corpus must be complete, neither projected out of the graph nor computed by the same analyzer that it evaluates. The oracle is still subject to human mistakes and limited corpus generalizability.

**Controls:** A positive corpus includes production-to-experimental source imports; an independent negative corpus contains a permitted production-to-stable dependency. The positive corpus also includes conditional/type-checking and dynamic-unresolved cases, which prevent the source engine from claiming complete assurance even if all labels match.

**Metrics (with denominators):** For each task, TP = exact overlap of expected/observed labeled tuples; FN = expected tuples absent; FP = observed tuples not expected; recall = TP/(TP+FN), precision = TP/(TP+FP). If the denominator is 0, the rate is null. A wrong target produces one FP and one FN. These rates are **fixture-agreement metrics**, not estimates of real-world false-positive/negative rates. Never average rates into a single quality score without representative sampling and appropriate confidence intervals.

**Adversarial checks:** Simulate modified gold labels, source mutation, extra/missing source files, altered report scores (even with a recomputed top-level digest), tampered sealed AE-01 source facts, source symlinks, unsafe publication paths, invalid selected test paths, missing validation profile and corrupted package ZIP checksums.

**Safety status:** `fixture_agreement_bounded` or `fixture_agreement_with_incomplete_assurance` or `gold_disagreement`. This **does not** override AE-01 `assurance_completeness`, `verified_compliance` or `rule_status`. In an unlabeled survey no precision, recall, defect detection or clean audit statement is permissible.

**Evidence chain:** source and gold bytes → AE-01 source manifest and verified source graph → G3 architecture obligations and receipts → AE-02 independently verified sealed generation → AE-08 comparison → replayable score with gold/source/policy hashes.

**Future work:** Build a manually curated, multi-repository blinded reference corpus with inter-annotator adjudication, representative defect classes, code review outcome linking, and statistical uncertainty reporting. AE-08 is a robust evaluation foundation, not yet such a population study.
