# AE-32C M7.5.9 — Validation Record

**Status:** Passed — exact-source GitHub Actions validation  
**Branch:** `stage1/section-uuids`  
**Validated source revision:** `121339f4816eb51df521a73d1a926bfeb7e12af2`  
**Workflow:** [Run 45903996222](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45903996222)  
**Workflow file:** `.github/workflows/m7_5_epistemic_contracts.yml`  
**Event:** `push`  
**Conclusion:** `success`  
**Runtime:** Ubuntu 24.04, Python 3.11

## 1. Results

| Suite | Passed |
|---|---:|
| M7.5.1 epistemic contracts | 14 |
| M7.5.2 append-only persistence | 9 |
| M7.5.3 completeness and negative-claim admissibility | 14 |
| M7.5.4 provenance and invalidation | 12 |
| M7.5.5 assurance arguments and defeaters | 8 |
| M7.5.6 recursive provenance freshness closure | 9 |
| M7.5.7 persisted assurance | 10 |
| M7.5.8 epistemic coverage and unknown-state assurance | 11 |
| M7.5.9 trusted rule-derived coverage | 10 |
| **Total** | **97** |

Epistemic package compilation passed. All nine suites passed.

## 2. M7.5.9 behaviors exercised

- all selected rule contracts derive evidence-kind and coverage obligations;
- built-in registry schema and digest are checked before derivation;
- unknown/ambiguous rules and duplicate rule selections fail closed;
- absence and mixed-polarity rules remain explicitly identified; no closed-world rule is added;
- unassessed derived obligations remain in the expected universe;
- callers cannot add obligations outside the derived universe;
- callers cannot shrink the derived expected universe;
- claim and source-snapshot binding is enforced;
- registry digest changes are rejected;
- plan fields are recomputed from the built-in registry before manifest construction and verification, rejecting forged plans.

## 3. Artifact

- Name: `m7-5-epistemic-validation-45903996222-1`
- Artifact ID: `15157530475`
- Size: 5,166 bytes
- SHA-256: `f51dc5b57f16fa2bef5014539eee49797d7ac406fffd44c3e1a588a0f8ee71e9`

The artifact contains the compile log and all nine suite logs.

## 4. Corrections during implementation

The first M7.5.9 workflow attempt exposed an import-side-effect defect: importing the rule-contract submodule initialized the AE-32C package and transitively imported the investigator's optional YAML dependency. AE-32C exports were changed to lazy loading so lightweight rule-contract imports remain isolated.

A subsequent run exposed doubled shell continuation characters in the new workflow step; these were corrected. The next run found a mismatch between the duplicate-rule error message and its test regex; the test was corrected. A final run against the exact source revision above passed. Earlier failed runs are excluded from the passing totals.

## 5. Assurance boundary

The result establishes behavior for the selected rule IDs and built-in registry at the validated source revision. It does not prove that the caller selected every applicable rule, that the source/extractor universe is exhaustive, or that the built-in registry has an externally authenticated author. Graph snapshot identity is retained in the plan, but the M7.5.8 manifest schema does not yet persist it. No negative-claim authorization, audit-gate transition or production approval is granted.
