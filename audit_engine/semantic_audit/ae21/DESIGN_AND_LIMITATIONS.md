# AE-21 / G9.23 — Externally Motivated Defect Pilot

## Study objective and preregistered boundaries

This is a **small feasibility pilot**, not a validated held-out benchmark of unseen repositories. The pilot separates: (i) byte admission, (ii) behavior under independently specified examples, (iii) AE-15 static observations, and (iv) interpretation. An oracle must not be derived from the analyzer's own prediction. A faithful oracle pair must not be counted as an auditor-detected defect. A non-detected bug is not automatically a *false clean* unless a specific scope and completeness contract asserted compliance.

### Source families

- **QB_GCD**: one QuixBugs challenge, defective/corrected GCD logic. Original public upstream: https://github.com/jkoppel/QuixBugs (`python_programs/gcd.py` and `correct_python_programs/gcd.py`), MIT license. The included programs are curator-made **semantic transcriptions**; they are **not upstream byte-for-byte files**, nor fixed at an authenticated upstream Git commit. Reference behavior: `math.gcd(35,21)=7`; defective implementation recurses until `RecursionError`, corrected returns `7`. A non-discriminating control `gcd(35,0)=35` passes in both. The defect is an *arithmetic/algorithmic fault* outside AE-15's claimed sound coverage.
- **SYN_BRANCH**: synthetic Python branch-local unbound `result`; defective `work(False)` raises `UnboundLocalError` and corrected returns `0`. Both return `5` for `True`. This exercises AE-15 possible-unbound analysis.
- **SYN_LOOP**: synthetic zero-iteration local unbound `result`; defective `work([])` raises `UnboundLocalError` and corrected returns `None`. Both return `7` for `[7]`. This exercises AE-15 possible-unbound analysis.

The 1 external example and 2 synthetic controls **must not be pooled into a statistically interpreted 3-case external accuracy score**. QuixBugs is a program-repair benchmark and does not automatically provide real incident/root-cause diagnoses. Labels are curator-authored, not blinded expert judgments. Not a randomized sample. No confidence intervals or population estimate justified.

## Registered outcomes

Before GitHub evaluation: require six exact approved `.py` fixture bytes and two fixed metadata/license documents; fail on changed contents, symlinks, extra members, or noncanonical `REFERENCE.json`. Only manual, explicit opt-in permits executing source. Gold observations are CPython exceptions or return values for positive and negative controls. Any missing or different behavior records `reference_oracle_failure`; avoid remapping labels to fit the analyzer. The static signal evaluates AE-15's own existing `possibly_unbound` source observations for the two synthetic pairs. Report TP/FP/FN/TN/unknown raw counts for those **four variants only**, preserving the external algorithmic pair as out-of-scope, NOT as a true negative.

## Trust, scope and reproducibility

1. Byte SHA-256 pins are in `ae21/evaluate.py`, distinct from editable `REFERENCE.json`. This prevents accidental and opportunistic rehashing of wrong labels from passing normal tests; hash equality still does not prove historical authorship.
2. Evaluator uses AE-01's actual inventory and AE-15's actual `analyze_snapshot`; no second graph engine. Does not invoke G3 to create receipts, findings, or proof of executable paths. Source spans and graph fingerprint are retained.
3. Test code invokes exact pinned fixtures with `exec` after explicit permission, **not in an OS sandbox**. Not safe for arbitrary external inputs, downloaded changes, or automatic pull request execution. Externally downloaded code **must not** be substituted into this executor.
4. `replay_equivalent` recomputes results from the exact code-pinned sources, not from editable reported checksums.
5. CI uses existing manual dispatcher, selected tests and `regression.enabled=true, path=tests/`; no new workflow, external network calls or secrets required.
6. Passing G9.23 establishes only pilot data admission, reference reproduction, honest metrics and compatibility. It does not establish performance on held-out unknown Python code, equivalence of semantic transcriptions to a specific QuixBugs commit, root-cause verification, C01–C15 completion, or production readiness.

## Research recommendation after this pilot

Before measuring external accuracy, independently choose a **larger stratified real-bug corpus** from a source such as BugsInPy (https://github.com/soarsmu/BugsInPy) with frozen Git commit IDs, actual upstream buggy/fixed source hashes, license attribution, independently adjudicated behavioral oracles, environment reproducibility, training/evaluation separation, no exposure of labels to analyzers, failure/abstention accounting and uncertainty intervals. This requires a separately authorized isolated execution environment; do not lift the AE-21 trusted in-process fixture executor into that workflow. For QuixBugs cross-check the maintained benchmark's limitations and known hanging cases before broad execution.
