# AE-22 / G9.24 — Protocol-governed effectiveness evidence

## Why a new phase is needed

AE-21 has one externally motivated algorithmic example **transcribed** from QuixBugs plus two locally authored scenarios. Although its tests are meaningful, their agreement cannot establish effectiveness on unfamiliar, independently adjudicated defects. AE-22 introduces a robust reusable *evaluation protocol and accounting layer*; it **does not manufacture a held-out sample** or a larger externally authenticated defect set.

## Admitted evidence / immutable identities

1. `PROTOCOL.json` freezes the declared objective, selection bias, non-blind status, analyst authority, and source execution prohibition.
2. `LABELS.json` declares ten source pairs (six bounded AE-15 cases, four deliberately outside scope), defect family, case provenance and absence of independent adjudication.
3. Every source and both reference records are hashed into a fixed code-level `PINNED_MEMBERS` map. Merely editing both source and an external checksum list cannot admit new bytes. A new dataset requires a new code/profile version and editorial review.
4. Filesystem admission refuses symlink paths, nonregular entries, added/removed members, large files and noncanonical JSON.
5. The effective `casebook_identity` hashes the admitted source map, labels and protocol together, so a report cannot be silently presented as another dataset.
6. The analyzer is AE-15's existing canonical SemanticGraph-backed bounded control/data-flow analysis, not a new program graph engine. No source is executed in AE-22.

## Scientific endpoint and denominators

The measured endpoint is **AE-15 possible-unbound static observation**, not verified defect, executed failure, or root cause. Each positive and control source receives one of:

- `possible_unbound`: a bounded source observation; counts as observed positive signal;
- `no_unbound_signal`: a negative observation within declared supported static scope; **not verified clean**;
- `unknown`: a missing/insufficient fact or unsupported precision in the relevant scope; always included as abstention;
- `out_of_scope`: the case is deliberately excluded from the AE-15 detector's intended semantics and counted in the whole-cohort accounting.

The aggregate reports an exact mutually exclusive 2×case-count partition. The confusion matrix uses only decided observations. It also reports the fraction of all admitted samples that received a decided static signal. Family-specific counts and descriptive Wilson intervals are provided; small, nonrandom selected cases do not justify population inference. No threshold on "accuracy" is encoded as a CI pass condition: low performance is valid research evidence.

## Provenance and benchmark contamination

- Nine pairs are author-created controls; one reproduces the previous GCD *semantic transcription* (not upstream-byte-authenticated). **Zero** upstream-byte-authenticated external cases and **zero** independently adjudicated cases are claimed.
- All cases are known to the team authoring the evaluator. Therefore `held_out_cases=0` and there is no valid assertion of blind evaluation.
- Reference source is labelled faulty or correct by the single curator, but AE-22 does **not execute** it. Behavioral oracle reproduction remains `NOT_RUN`. AE-21 may have reproduced selected controls separately, which does not upgrade the new casebook's authority.
- Even if some cases have identical names to externally published benchmarks, name and a URL do not authenticate upstream version or ensure license/source compatibility. Upstream SHA-256 plus immutable upstream commit and independently checked behavior are required for a stronger grade.
- Failure to signal a valid out-of-scope algorithmic bug is not a false negative **within AE-15's declared scope**. It remains visible as out-of-scope; the whole dataset coverage denominator is not quietly shrunk.
- No analyzer output or advisory text is treated as a security permission, solver proof, verified finding, or root-cause diagnosis.

## Security and workflow

- GitHub manual validation only. No network fetch, checkout of external repositories, test-source execution, `exec`, `eval`, or subprocess in the AE-22 evaluator.
- Uses existing AE-01 source inventory and AE-15 graph facts. New report is a deterministic observation document, independently reproducible from the code-pinned casebook.
- Input `source` and source code files are considered untrusted except for explicit exact-byte fixture admission. Hashing is integrity, not remote-origin authentication.
- No changes to GitHub workflows, `main`, G3 finding authority, memory stores, or existing application execution permissions.

## Promotion to an external held-out benchmark — separate later milestone

Requires a **pre-registered sample** from an external Python defect database (e.g. BugsInPy), original and fixed commit IDs, original source bytes and hashes verified against those commits, license/admissibility review, two independent adjudicators where feasible, independently runnable failing/passing tests in an isolated environment, control pairs including hard negatives, a blinded scoring protocol, and a reproducible selection/exclusion ledger. `unknown`, `out_of_scope`, timeouts, and unsupported environments must remain visible. Evaluation should stratify by defect family and repository, avoid train/test leakage, and only make population claims justified by actual sample design and size. This release supplies the accounting and integrity machinery, not those future missing ingredients.
