# AE-37 — Negative-Control and Dynamic-Contract Runtime Checks

**Status:** Validated; exact-head Actions workflow passed  
**Branch:** \`stage1/section-uuids\`  
**Scope:** AE-32D verifier calibration; no benchmark scoring

## 1. Purpose

A verifier that only reproduces the positive fixture can be overfit to one expected exception. Add software checks for two contrasting outcomes: a valid no-defect provider contract and a dynamic attribute implementation that makes the same consumer access valid at runtime.

## 2. Added controls

- **Negative control:** extractor reads \`provider.calls\`; adapter initializes that member. The controlled runtime must exit successfully.
- **Dynamic-contract ambiguity control:** extractor reads \`provider.total_calls\`; adapter implements \`__getattr__\` to expose the counter dynamically. Runtime must succeed, while the fixed defect verifier must refuse to infer member absence and fail closed.

The runtime harness now has explicit expected-success and expected-AttributeError modes. The production CLI continues to use only the fixed historical candidate and expects the pinned defect reproduction.

## 3. Exact-head validation

- Commit: `8a3db63977bfe039b485e8fcb939d1f48a906a39`.
- AE-32D workflow: [run 46005438275](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/46005438275), success; 4 benchmark-gate tests and 11 verifier-boundary tests passed; immutable candidate verification passed.
- Artifact: ID `15201860660`, archive SHA-256 `a01a2d7670ff3344f4e3cffbfd5b8064ad2954238ee8c8cc8b9b9fa55d4876a6`.
- AE-32C source/graph regression: [run 46005438313](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/46005438313), success.

## 4. Assurance boundary

These are verifier-calibration tests, not scored benchmark cases. They demonstrate that successful runtime behavior and static absence inference are treated separately. They do not prove complete Python semantic analysis or general benchmark accuracy.
