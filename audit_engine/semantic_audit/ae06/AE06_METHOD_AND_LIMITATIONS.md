# AE-06 — Evidence-Bound Remediation Closure and Regression Guard

## Scientific purpose

A confirmed architecture-rule finding at audit generation **F** is not closed merely because a later audit has fewer findings. AE-06 evaluates whether the **same source/rule target** remains in a comparable, independently verified generation **C**, and whether the prior violation was acknowledged for investigation in a verified AE-05 review journal. It emits *bounded absence candidates*, not certified repairs.

## Input assurance chain

1. Read and independently validate three AE-01 generations: original pre-violation, flagged, follow-up. Each is source-byte, graph, policy, and receipt bound by the existing AE-01/AE-02 verification stack.
2. Verify the original AE-04 campaign connects original → flagged and the AE-05 published review is bound to precisely that campaign. Parse only the fully sealed AE-05 latest generation.
3. Independently verify the follow-up AE-04 campaign connects flagged → follow-up, including impact propagation and declared policy/coverage.
4. For optional regression history, verify each adjacent pair through a *published* AE-04 campaign; reject arbitrary, non-adjacent, repeated or oversized histories. A history chain establishes structural sequence, **not authoritative clock chronology**.
5. Compare finding-rule identity, source module, internal-import target, source bytes, whole lifecycle configuration (including exclusions/AST environment), source manifest completeness, and actual source-rule obligations/receipts.
6. Recompute conclusions from the primary sealed evidence in `verify_assessment()`. Never accept a signed or rehashed output as an independent oracle by itself.

## Case states

- `persistent_violation`: same forbidden internal dependency still verified.
- `reintroduced_violation`: same verified forbidden dependency appears after an explicitly linked, comparably assessed intermediate generation without that exact finding; *logical sequence only*.
- `changed_violation_open`: same source module still has another verified policy violation.
- `bounded_absence_candidate`: former forbidden dependency is absent in a compatible and **executed** current policy assessment, the source changed, old target remains in source scope, and a corresponding AE-05 `requires_action` event exists.
- `not_assessable`: rule, classification, scope, execution, source or target identity cannot be compared responsibly.
- `review_required`: evidence is comparable but the original finding lacks an applicable human `requires_action` record.

A *bounded absence candidate* does not prove the source change caused remediation. It requires separate review and is not automatically promoted into AE-05 closure, approval, production deployment, or a correctness guarantee. Verified policy violations anywhere in the current generation remain open.

## Evidence and publication

`assessment_sha256` is a deterministic canonical-record identity, not an authenticity signature. Every record contains exact AE-01 generation/seal identities, AE-04 campaign hashes, AE-05 review/journal hashes, historical link hashes, source/witness hashes, per-finding outcomes and explicit limitations. A complete publication is committed as a content-addressed generation; the `LATEST.json` pointer is fail-closed under a file lock. The independent verifier re-derives and compares the complete assessment from primary publications.

Historical generations are intentionally evaluated as historical evidence and are not checked against a live working tree unless independently requested at AE-01 creation/verification time. AE-06 cannot authenticate reviewer identity or establish production code runtime semantics, mutation equivalence, arbitrary dynamic import behavior, or remediation causality. File locks assume a trusted, conventional local filesystem and do not provide a distributed transaction mechanism or cryptographic signatures.

## Manual workflow

```shell
python -m audit_engine.semantic_audit.ae06 publish \
  --origin-before /audits/base --flagged-output /audits/bad \
  --current-output /audits/remediated \
  --origin-campaign /campaigns/original --origin-review /reviews/original \
  --followup-campaign /campaigns/followup --output /audits/remediation_review
python -m audit_engine.semantic_audit.ae06 verify \
  --origin-before /audits/base --flagged-output /audits/bad \
  --current-output /audits/remediated \
  --origin-campaign /campaigns/original --origin-review /reviews/original \
  --followup-campaign /campaigns/followup --output /audits/remediation_review
```

For a regression chain, add each ordered `--history-output` and the `N + 1` matching `--history-campaign` paths. Experiments remain read-only against input/source publications; only an explicit AE-06 output directory is modified.

## Acceptance discipline

Use real sealed fixtures and independent expected signatures; include permitted and forbidden imports, incomplete/unknown source scope, changed policies, missing obligations, human disputes, follow-up publication failures, corrupted archives, symlink escapes, recovered generations, and known reintroduction. The passing G9.7 profile validates the integration contract, **not** universal absence of defects. GitHub acceptance must be established from the user's remote run logs.
