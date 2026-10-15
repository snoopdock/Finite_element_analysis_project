# AE-20 — Actual project regression cases and independent Python behavior controls

**Status:** prepared for GitHub G9.22, not yet tested.

## Grounded evidence classes

The three before/after pairs in `ae20_faults/snapshots/` were extracted **byte-for-byte** from the user-provided release archives:

- E01: AE-18 before G9.20 missing-evidence correction vs AE-18.1 after correction. This is an actual Python implementation defect: Git omits empty directories, and original evaluator passed a nonexistent root into the correctly defensive AE-16 verifier. The replay forcibly represents the omitted empty directory on a temporary copy, leaving the canonical corpus unchanged.
- E02: AE-19 reference labels before/after the failed G9.21 catalog label correction. This is a **reference/oracle data defect**, not a code-level defect. Failed run publication was mistakenly labeled as successful catalog verification.
- E03: AE-19.1 reference JSON vs AE-19.2 canonical JSON. This is a **data serialization / release-packaging defect**, not a novel code defect. The previous correction emitted JSON without its mandatory final newline.

Each snapshot hash is baked into `evaluate.py`; rewriting `MANIFEST.json` or updating a casebook SHA does not authorize changing executable snapshots. The evaluator asserts source identity and compares actual reproducible behavior against explicitly declared independent reference outcomes. A mismatch fails the gate without promoting any root cause to verified status.

The supplementary `test_ae20_behavioral_oracles.py` uses Python's own interpreter and `symtable` as an oracle to test shadowed function dispatch, locally shadowed type guards, potentially unbound variables, and incomplete control-flow claims. **These are controlled synthetic programs**, not independently verified historical incidents. Test results are code behavior checks, not complete Python semantic correctness.

## Execution trust boundary

- The evaluator runs exactly two imported historical AE-18 module snapshots via `runpy`, gated by source hash allowlist and explicit opt-in.
- This is **not** OS-level sandboxing. It is intended exclusively for the explicitly approved manual GitHub tests using committed trusted test code. It must not be reused for untrusted pull requests, retrieved code, models' generated snippets, or arbitrary user archives.
- Actual casebook declarations do not become instructions. AE-16/17 analyze them as untrusted observations.
- No root cause is verified by concordance alone; the known historical bugs are **reviewed from the supplied logs and patch diffs**, not proven as unknown-cause discoveries by AE-17.

## Benchmark validity

This evaluates **one actual code-level defect, one incorrect reference label, one serialization error**, and additional synthetic behavioral controls. It does not yield a general-purpose code-audit precision/recall estimate: there is no sampled representative population and no independently adjudicated external repository collection. The original C01–C15 charter still governs readiness.

The G9.21 GitHub evidence log showed passing selected tests, `tests/` regression, detached verification, CAS publication and catalog verification. The snapshots originate from previously supplied release archives. These bytes are not GitHub API-authenticated source blobs. Future external benchmarking should use reviewed commit-pinned upstream bug/fix pairs, held-out projects and independently annotated root-cause evidence.
