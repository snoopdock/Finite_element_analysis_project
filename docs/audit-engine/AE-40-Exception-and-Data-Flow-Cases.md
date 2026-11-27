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
