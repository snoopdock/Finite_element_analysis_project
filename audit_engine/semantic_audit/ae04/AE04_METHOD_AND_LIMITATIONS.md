# AE-04: Evidence-bound assurance campaign — methodology and limitations

## Question and explicit scope

AE-04 asks **which source-bound architecture policies were actually evaluated, what changed between sealed generations, which modules merit human re-verification, and whether independently replayed selected mutation trials expose weak tests?** It does not certify scientific correctness, whole-program safety, or arbitrary dynamic import behavior.

## Independent evidence hierarchy

1. Historical AE-01 generations are loaded using AE-02's existing detached source/graph/rule verification. A stale or failed `LATEST` pointer cannot be interpreted as a passing current generation. Explicit generation selection remains possible for historical comparisons.
2. Existing AE-02/2.1 derives the change delta, graph evolution, source-impact propagation, exact import witness index, and policy coverage from those sealed generations. AE-04 does **not** fabricate call edges or replace G3 verification.
3. Optional AE-03 evidence is source-byte checked against the **current** AE-01 generation, workspace-hash verified, and **outcome-replayed**. If AE-03 provenance includes an impact scope, it is recomputed using the existing `verified_impact` adapter and compared to the embedded claims. No source-tree mutation is performed by AE-04.
4. A deterministic review register prioritizes *verified policy findings* (P0), *full-scope rechecks* (P1), *direct changed modules* (P2), and *historical/current import dependents* (P3). These priorities are discrete workflow conventions, **not probabilities of faults**.
5. Campaign publication uses SHA-256 artifact content identities, fsync-backed atomic member writes, atomic generation staging and a failure-invalidating `LATEST` pointer. Verification recomputes the decision from independent evidence; hashing alone never elevates a claim.

## Decision model

- `verified_policy_violation_requires_review`: independently verified architecture finding(s) in the successor generation.
- `inconclusive_scope_requires_review`: architecture/policy coverage incomplete, truncated impact, or required/replayed mutation evidence incomplete.
- `test_effectiveness_review_required`: selected valid mutation survives, despite a passing baseline. It is not a production defect claim.
- `change_review_required`: source/policy changed; bounded, manual re-review tasks exist.
- `bounded_architecture_policy_pass`: **only** no detected changes or findings, complete declared architecture policy coverage, no exhausted impact budget, and no outstanding required mutation evidence. **Not** a global quality certificate.

There is no autonomous code modification or autonomous acceptance. CI exit code `0` is reserved for bounded policy pass and detached verification, `3` means a verified but non-passing/review-required decision, and `4` means execution/evidence error.

## Assurance caveats

- AE-01 may report incomplete scans for unresolved imports, encoding errors or missing lifecycle classifications. Those results cannot be promoted to compliance.
- Python dynamic dispatch, undeclared imports, concurrency and native extension effects remain outside the static import model.
- Audit generation order is selected by the caller, **not** inferred from timestamps or authenticated Git history.
- Evidence SHA-256 seals detect unexpected changes relative to their accompanying manifests; they are not signed external attestations and cannot stop a privileged adversary who can replace an entire evidence set. Source-control commit verification must happen separately.
- A mutation score is descriptive for the selected operator family, source files and tests. Surviving mutants can be equivalent or out of scope. Killed mutants are not proof of all meaningful faults being detected.
- Running trusted tests in copied workspaces is **not** a security sandbox. Use a secured CI environment with untrusted/networked side effects disabled by policy. Mutation replay is intentionally explicit and never automatic during ordinary evidence-only verification.
- A clean `bounded_architecture_policy_pass` must never be reported as a repository-wide security or scientific correctness certificate.

## Reproducibility

`python -m audit_engine.semantic_audit.ae04 run --before-output PATH --after-output PATH --output NEW_PATH`

`python -m audit_engine.semantic_audit.ae04 verify --before-output PATH --after-output PATH --output NEW_PATH`

Add `--mutation-record PATH --mutation-root PATH --replay-mutation` for an explicitly permitted trusted-test experiment. `--require-mutation` holds the decision inconclusive if no replayed record is supplied. Review the campaign JSON and detached verification receipt before any human acceptance.
