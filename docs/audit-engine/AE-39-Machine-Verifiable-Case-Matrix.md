# AE-39 — Machine-verifiable case matrix

## Scope

AE-39 expands the AE-32D candidate inventory from one provider-interface regression to four records, covering three additional controlled case families:

1. **Control-flow defect:** conditional assignment followed by unconditional return; the false branch reproduces an `UnboundLocalError`.
2. **No-defect negative control:** a local is initialized before the conditional and both documented input paths return their expected values.
3. **Insufficient-evidence / ambiguity control:** the visible consumer reads `total_calls`, the visible adapter maintains `calls`, and the factory imports a provider implementation absent from the evidence bundle. The verifier checks this evidence boundary and deliberately does not execute the unavailable implementation.

The existing provider-interface regression remains in the inventory. All three new cases point to the immutable fixture-source commit `dd80be6e7a3e0a912beace92ce0fac446ea6ed61`. The workflow checks out that exact commit separately and verifies its Git HEAD before examining the fixtures.

## Machine-verification semantics

- The control-flow case must satisfy its AST and contract checks and reproduce the false-branch runtime exception.
- The no-defect control must satisfy its initialization structure and execute both contract paths as `[5, 0]`.
- The ambiguity control must establish both the visible name difference and the absence of the factory's imported implementation from the supplied evidence. It must not claim a runtime defect.
- Every file's SHA-256 is included in the generated matrix report.
- The verifier reports `primary_benchmark_eligible: false` and `human_independent_adjudication: not_performed`.

## Benchmark and scoring gates

All newly added records remain `candidate`, with `ground_truth.label=pending_adjudication`, review pending, and primary eligibility false. The no-defect and ambiguity cases are deliberately not promoted to gold labels by fixture construction or machine checks. The deterministic outcome classifier can classify only already-adjudicated labels; it cannot adjudicate these records.

The inventory now has four cases, but the pilot target remains 6–10. Two further distinct case families and the required adjudication/freeze work remain before any primary benchmark score can be reported.

## Validation

The AE-32D workflow validates the case manifest and pilot counts, tests the verifier's three case-specific behaviors, and runs the matrix verifier against the pinned source checkout. A passing run establishes fixture-level machine checks only; it does not establish model performance or independent semantic ground truth.

## Executed validation record

- AE-32D workflow: [run 46010190530](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/46010190530) — completed successfully on verifier revision `a9ba87b36ad2f84611f2df9a86802467d9eb5860`.
- Pinned fixture source: `dd80be6e7a3e0a912beace92ce0fac446ea6ed61`.
- Matrix result: `machine_verified_matrix`; branch-unbound `verified`; no-defect `verified`; ambiguous-provider `ambiguity_boundary_verified`; zero verifier errors.
- The workflow's outcome-classifier tests, three matrix tests, benchmark-record validation tests, fixed-fixture boundary tests, and existing provider-interface verification all passed.
- An earlier run on the immediately preceding verifier revision failed because Python isolated mode excluded the fixture directory from import resolution. The runtime harness was corrected to use a reduced environment without `-I`; the subsequent run above passed. This failure and correction are retained rather than hidden.
