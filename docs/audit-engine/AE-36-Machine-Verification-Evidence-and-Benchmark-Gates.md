# AE-36 — Machine-Verification Evidence Ledger and Benchmark Gate Validation

**Status:** Validated; exact-head Actions workflow passed  
**Branch:** \`stage1/section-uuids\`  
**Scope:** AE-32D case provenance, machine-verification records, and fail-closed benchmark eligibility

## 1. Machine-verification record

The provider-interface fixture is now recorded as \`machine_verified_regression\`. Its evidence points to the exact candidate source commit, verifier commit, successful workflow run, artifact identifier and archive digest, nine passing boundary tests, six machine checks, and reproduced runtime status.

The case's original ground-truth label remains \`pending_adjudication\`. Machine verification is a distinct evidence lane: it confirms the controlled fixture's declared runtime failure, but it does not become a benchmark gold label or grant primary-score eligibility.

## 2. Deterministic record validation

New JSON Schemas cover the scoring rubric and pilot plan. The case schema permits a typed machine-verification record and the distinct \`machine_verified_regression\` status. The manifest schema uses the same status.

The read-only validator checks schema validity, manifest-to-case identity and status consistency, duplicate IDs and paths, path traversal, pilot-plan case counts, machine-source identity, and the rule that machine verification cannot grant primary benchmark eligibility. Primary scoring remains blocked unless labels and adjudication records are complete and the manifest, rubric, and pilot plan are frozen.

The validator does not change case labels, score model outputs, or call an LLM.

## 3. Exact-head validation

- AE-32D machine verification and record validation: [run 46005165350](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/46005165350), success.
- AE-32C source/graph regression: [run 46005165371](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/46005165371), success.
- Machine-verification artifact: ID `15201940266`, archive SHA-256 `2521601b3ef4bb479a148c7ae353968885f95167ae52b26a1f2c30968158a539`.

## 4. Current status

Machine-verification evidence is complete for this one fixture. The benchmark remains \`design_only\`; the rubric and pilot plan remain drafts; no primary score is permitted. Next deterministic work is to build negative-control and ambiguous fixtures and validate their declared expected outcomes before adding model comparisons.
