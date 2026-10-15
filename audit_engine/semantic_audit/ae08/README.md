# AE-08 — Independent Semantic Audit Effectiveness Evaluation

## Operational purpose
AE-08 measures a bounded version of *source-observation fidelity* and *architecture-finding agreement* against separately annotated, exact-byte fixture sources. It reuses **AE-01** for source-graph/rule execution and **AE-02** for independent verification of the sealed AE-01 generation. No duplicate semantic graph implementation is introduced.

### Boundaries
- The gold corpus is **manually labeled** and cryptographically bound to a complete closed-world fixture inventory. Expectations are not automatically generated from ASTExtractor or the graph verifier under test.
- Exact occurrence comparison uses path, line, column, import form, module, symbol, alias, context, resolution status and target. This makes a wrong target a missing expected observation **and** an unexpected observed observation.
- Verified findings are compared by occurrence location and resolved target; all findings are independently checked by the AE-02 publication verifier before scoring.
- `precision` and `recall` are defined **only over the labeled corpus**, with explicit numerator/denominator. Undefined denominators produce `null`, not fictitious 100% scores.
- A fully matched gold corpus is **not** sufficient for a compliant/clean verdict if AE-01 reports unsupported import semantics, unresolved bindings, conditional imports, missing lifecycle classification or incomplete source scope.
- The real-repository `survey` command generates **descriptive** source/import counts and explicitly refuses to calculate precision/recall or compliance from unlabeled source code.
- Gold labels reflect human-written tests, not independently adjudicated historical software defects. The fixtures are tiny, illustrative, and not representative of the project's production defect distribution.

## Manual commands
Run from repository root (never automatically on Git push):

```bash
python -m audit_engine.semantic_audit.ae08 evaluate \
  --source-root tests/fixtures/ae08_gold \
  --gold tests/fixtures/ae08_gold/gold.json \
  --policy specs/rules/architecture/no_production_to_experimental_dependency.yaml \
  --audit-output /tmp/ae08-gold-audit \
  --report /tmp/ae08-gold-score.json
python -m audit_engine.semantic_audit.ae08 verify \
  --source-root tests/fixtures/ae08_gold \
  --gold tests/fixtures/ae08_gold/gold.json \
  --policy specs/rules/architecture/no_production_to_experimental_dependency.yaml \
  --audit-output /tmp/ae08-gold-audit \
  --report /tmp/ae08-gold-score.json
python -m audit_engine.semantic_audit.ae08 survey \
  --source-root . \
  --report /tmp/ae08-repository-survey.json
```

Note: `evaluate` exits 2 when independently labeled expectations disagree with the engine; 4 on invalid input or verification errors. `survey` does not execute architecture policies and **does not claim repository compliance**.

## Independent reproducibility
Evaluation reports include the gold manifest digest, policy digest, source manifest digest, sealed publication digest, source-bound occurrence matches and a deterministic report digest. The `verify` command checks the complete original source and policy bytes, natively verifies the AE-01 generation, recalculates all metrics and rejects both altered labels and resealed fabricated scorecards.

## Constraints and known limitations
- Only Python source-observation and the pinned `no_production_to_experimental_dependency` architecture policy are measured.
- The small fixtures contain positive, negative, aliased, relative, duplicate, type-only and dynamic cases, but they are not a calibrated statistical sample. Do not generalize their 100% fixture agreement to unseen code.
- Dynamic dispatch, imports with runtime side effects, and scientific algorithm correctness are outside AE-08's ground truth.
- The unlabeled repository survey intentionally provides no review finding; its counts may include imports not executed at runtime and external imports that are not installed in the execution environment.
- No model or AI inference of module lifecycle is used. Human-approved policy classifications remain necessary for actual repository audit conclusions.
- The executable tests run trusted source in disposable directories; this is not a security sandbox for arbitrary adversarial programs.
