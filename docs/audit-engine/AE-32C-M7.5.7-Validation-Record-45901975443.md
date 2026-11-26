# AE-32C M7.5.7 — Validation Record

**Status:** Passed — exact-source GitHub Actions validation  
**Branch:** `stage1/section-uuids`  
**Validated source revision:** `dbe2f63aa9756408883019380bfaf3df09e05191`  
**Workflow:** [Run 45901975443](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45901975443)  
**Workflow file:** `.github/workflows/m7_5_epistemic_contracts.yml`  
**Event:** `push`  
**Conclusion:** `success`  
**Attempt:** 1  
**Runtime:** Ubuntu 24.04, Python 3.11

## 1. Job and step results

Job: `M7.5.1–M7.5.7 structural and behavioral validation`

All steps completed successfully:

1. Checkout exact triggering revision.
2. Set up Python 3.11.
3. Compile the epistemic package.
4. Run M7.5.1 contract tests.
5. Run M7.5.2 persistence tests.
6. Run M7.5.3 completeness and negative-claim tests.
7. Run M7.5.4 provenance and invalidation tests.
8. Run M7.5.5 assurance argument and defeater tests.
9. Run M7.5.6 recursive freshness closure tests.
10. Run M7.5.7 persisted assurance tests.
11. Upload exact-source validation logs.
12. Summarize validation boundary.

## 2. Test results

| Suite | Tests passed |
|---|---:|
| M7.5.1 epistemic contracts | 14 |
| M7.5.2 append-only epistemic persistence | 9 |
| M7.5.3 completeness and negative-claim admissibility | 14 |
| M7.5.4 provenance and invalidation | 12 |
| M7.5.5 assurance arguments and defeaters | 8 |
| M7.5.6 recursive provenance freshness closure | 9 |
| M7.5.7 provenance-backed persisted assurance | 10 |
| **Total** | **76** |

All 76 tests passed. Python 3.11 compileall passed with no diagnostics. The downloaded artifact archive was inspected; each suite log reports the expected count and `OK`.

## 3. Artifact

- Name: `m7-5-epistemic-validation-45901975443-1`
- Artifact ID: `15156087476`
- Size: 4,076 bytes
- SHA-256: `bb509455cf69092ff7c1bcfad8fde5d14618684e32f763a0c6bdc64f45c161c2`
- Contents:
  - `m75-compile.log`
  - `m75-1-epistemic-contracts.log`
  - `m75-2-epistemic-store.log`
  - `m75-3-completeness.log`
  - `m75-4-provenance.log`
  - `m75-5-assurance-arguments.log`
  - `m75-6-freshness-closure.log`
  - `m75-7-persisted-assurance.log`

## 4. M7.5.7 behaviors validated

The dedicated suite verifies:

- typed assurance records can be reconstructed from the verified assurance ledger;
- persisted evidence IDs are resolved against EvidenceAssertion records;
- proposition and scope binding is enforced;
- source-snapshot binding is enforced;
- evidence provenance edges must match the persisted EvidenceRef metadata;
- evidence nodes and link provenance nodes must have recursively fresh closures;
- missing terminal manifests remain `UNKNOWN`;
- transitive invalidation blocks the assessment;
- conflicting evidence metadata and absent evidence fail closed;
- defeater-resolution evidence is also required to be persisted and fresh;
- a ledger mutation during evaluation is detected by the cross-ledger version-token check;
- absent assurance claims return `INCOMPLETE`.

## 5. What this establishes

For the exact source revision above, CI establishes that the M7.5.1–M7.5.7 regression and dedicated test suites pass under Python 3.11, and that the workflow produced all eight expected logs.

The M7.5.7 evaluator now derives evidence availability from persisted EvidenceRefs and freshness from `freshness_closure()`; it does not accept caller-supplied evidence/freshness maps as the authority for this store-backed path.

## 6. What this does not establish

This is CI validation, not production approval. It does not establish:

- a shared atomic transaction across the two SQLite ledgers;
- distributed consensus or administrator-resistant tamper proof;
- signed or externally anchored evidence/provenance;
- independent verification of source URIs, producer identity, method identity or artifact bytes;
- exhaustiveness of the evidence dependency schema;
- evidence independence;
- completeness or soundness of argument/defeater discovery;
- formal premise/warrant registry validation;
- proposition truth, probability, confidence or authorization for audit-gate transitions.

## 7. Documentation follow-up validation

After the specification was updated with the exact M7.5.7 result, the documentation commit `50375230658377e6c427f92e6f9518052c581cd1` triggered the same workflow again.

- Follow-up run: [45902084056](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45902084056)
- Conclusion: `success`
- Exact tested revision: `50375230658377e6c427f92e6f9518052c581cd1`
- All compile and seven test-suite steps succeeded.
- Test counts remained 76 total, including 10 M7.5.7 tests.
- Artifact: `m7-5-epistemic-validation-45902084056-1`
- Artifact ID: `15155468620`
- Artifact SHA-256: `24bf5ee8d92363a3d4f99907f8e23bb95992e3a5040f25bd3b456aacd85d7a82`

The original run validates the implementation source revision `dbe2f63aa9756408883019380bfaf3df09e05191`. The follow-up run confirms the specification update did not break the combined workflow.

## 8. Reproducibility

- [Validated source commit](https://github.com/snoopdock/Finite_element_analysis_project/commit/dbe2f63aa9756408883019380bfaf3df09e05191)
- [Workflow run](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45901975443)
- [Workflow definition](https://github.com/snoopdock/Finite_element_analysis_project/blob/stage1/section-uuids/.github/workflows/m7_5_epistemic_contracts.yml)
- [M7.5.7 specification](AE-32C-M7.5.7-Provenance-Backed-Assurance-Evaluation.md)
