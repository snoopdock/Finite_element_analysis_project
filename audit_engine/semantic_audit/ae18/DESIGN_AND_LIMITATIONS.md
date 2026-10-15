# AE-18 — Independent controlled effectiveness evaluation

## Mission

Independently evaluate the **bounded AE-16 / AE-17 operational slice** against a static, explicitly labeled reference corpus. This is *not* a claim of completion for C01–C15, a security certification, or a causal root-cause benchmark.

## Independence and authority

- `fixtures/ae18_reference/cases/` contains twelve source-like execution declarations and evidence bytes, with manual expected issue identities defined separately in `labels.json`.
- `MANIFEST.json` binds *exact bytes*, including the reference labels. No expected label is synthesized by AE-16 or AE-17.
- Labels were manually constructed for this controlled evaluation, not externally adjudicated. Their SHA-256 checksums establish fixture integrity, **not impartial authorship**.
- The evaluator invokes the **existing** AE-16 and AE-17 publication and independent replay paths, then compares exact `(kind, subject)` issue identities.
- Correct successful controls, expected failing nested tests, skipped mandatory checks, missing logs, missing artifacts, exit-state inconsistencies, unexpected nested-test outcomes, artifact discrepancies and job dependency discrepancies are covered.
- Evaluation outputs never contain verified findings or verified causes; AE-17 plans are unverified and do not execute tests or suggested investigations.

## Scores and publication

- Exact-case match, true-positive, false-positive, false-negative, precision, recall, false clean, false alarm, correct clean controls, and issue-to-hypothesis plan coverage are all reported.
- Undefined metric denominators produce `null`, not an invented 100%.
- Strict candidate acceptance requires *all* reference cases to match and plans to account for all issue identities without truncation. This acceptance applies only to the controlled corpus.
- Evaluation publication binds `MANIFEST.json`, `labels.json` and the output report to content-addressed, replayable generations; the report is regenerated from the source corpus during verification.

## Deferred effectiveness requirements

- Independently reviewed *historical real failures*, authenticated workflow telemetry, broader Python code semantics, and controlled fault-injection experiments are not part of G9.20.
- G3 verified findings, mutation testing/oracle strength, AE-09 traceback causal accuracy, AE-14/15 general data-flow detection, cross-repository false-positive rates, and the complete original C01–C15 acceptance matrix require separate work.
- This patch does not claim external performance, production memory scaling, completeness of the five audit modes, or automatic remediation safety.

## Resource and trust boundaries

- Manifests are strict and checksummed; missing/extra members, symlinks, unsafe paths, duplicate labels and oversized entries are rejected.
- All fixture contents are data; no commands declared in the fixtures are executed. The benchmark runs the installed analyzer implementation in the explicitly authorized GitHub test environment.
- The evaluation runner writes only to an explicitly supplied output directory outside the corpus.
- Existing GitHub validation is **manual only** and the selected `G9.20` profile also requests the declared full `tests/` regression.
