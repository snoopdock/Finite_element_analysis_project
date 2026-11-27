# AE-40 — Exception-flow and data-flow case families

## Additions

AE-40 adds two synthetic defect candidates to the AE-32D matrix.

- **Exception-flow defect:** `load_config` catches `OSError` and returns an empty mapping even though the declared contract requires propagation. The verifier checks the AST handler and reproduces the swallowed exception with a deterministic reader.
- **Stale-value data-flow defect:** `invoice_total` computes a discounted intermediate but the return sink consumes the original subtotal. The verifier checks the intermediate/sink relationship and reproduces 105 where the declared result is 95.

Both fixture sets are pinned to `c0d700c0a2599aabda8957f54e750a812ea2ef5d`, checked out separately by the AE-32D workflow, and hashed in the verification report. Their records remain candidates with pending ground truth and no primary-score eligibility.

## Matrix state

The inventory now has six records: provider-interface regression, branch-unbound control-flow defect, no-defect negative control, ambiguous provider evidence, exception suppression, and stale-value data flow. This reaches the numeric lower bound of the 6–10-case pilot target, but does not satisfy adjudication, rubric approval, or benchmark freeze gates. No benchmark score is authorized.

## Validation boundaries

A passing verifier confirms only that the pinned synthetic fixtures exhibit their declared structural/runtime properties. It does not establish that an audit condition detects them correctly. It does not establish the correctness of a general diagnosis, and it does not turn the candidate labels into gold labels.

## Executed validation record

- AE-32D workflow: [run 46010847618](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/46010847618) — completed successfully on verifier revision `9ac8182ac32a0d5a7cd2c99c011220810fddb1de`.
- Extended fixture source pin: `c0d700c0a2599aabda8957f54e750a812ea2ef5d`.
- Both added cases reported `verified`, with no verifier errors.
- The run also passed the original three-case matrix, outcome-classifier tests, benchmark-record validator, fixed-fixture boundary tests, and provider-interface verification.
- Artifact ID: `15204151762`; archive SHA-256: `46ac1ba5dfc427e4d4036ca771c46260e391b745c9afb69ece58ef0555ebc41b`.
- An earlier attempt exposed an invalid runtime harness statement that combined an import and compound `try` statement on one line. The harness was corrected to separate the import from the `try` block; the successful run above verifies the corrected behavior.
