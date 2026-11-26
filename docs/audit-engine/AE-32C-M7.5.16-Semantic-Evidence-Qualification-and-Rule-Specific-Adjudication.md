# AE-32C M7.5.16 — Semantic Evidence Qualification and Rule-Specific Adjudication

**Status:** Implemented; exact-source CI validation pending  
**Branch:** `stage1/section-uuids`  
**Parent:** M7.5.15 — Typed Evidence Observations and Rule-Obligation Binding  
**Authority:** narrow, rule-specific evidence qualification only; no proposition-wide truth or audit-decision authority

## 1. Purpose and boundary

M7.5.15 established source-bound structural observations and bound them to evidence-kind obligations. M7.5.16 adds a second, independent layer: a versioned semantic evidence contract registry and validators that replay selected observations against exact source bytes and a verified rule-derived coverage plan.

The implementation preserves these distinctions:

1. A structural observation exists.
2. The observation's identity, source reference, and narrow structural meaning are independently replayed.
3. The observation is evaluated against a specific rule/evidence contract.
4. A narrow proposition may be supported, insufficient, contested, or unknown.

A successful validator does not automatically satisfy the whole rule obligation, establish the broader proposition, create an epistemic assertion, resolve a dossier gap, or authorize an audit decision.

## 2. Implemented rule-specific contracts

The initial registry is deliberately small and versioned:

| Rule | Evidence kind | Qualification | Narrow interpretation |
|---|---|---|---|
| `AE32A-GRAPH-SERVICE-UNUSED` | `graph_import` | `INSUFFICIENT` | A verified import is not proof of service use or non-use |
| `AE32A-GRAPH-NOT-IN-LLM-PATH` | `graph_import` | `INSUFFICIENT` | An import cannot establish execution-path or data-flow absence |
| `AE32A-INCOMPLETE-PYTHON-SCAN` | `python_syntax_error` | `SUPPORTED` | Exact source bytes independently reproduce the AST parse failure, supporting a parse-coverage limitation only |
| `AE32A-SCOPE-EXCLUSIONS` | `scope_exclusion` | `INSUFFICIENT` | The observation alone does not independently replay the upstream exclusion inventory or establish scope adequacy |

The `SUPPORTED` result for Python syntax failure is intentionally narrow. It does not assert that the source has any other defect. The scope-exclusion observation remains insufficient until the upstream inventory and its exclusion-selection semantics are independently replayed by a dedicated validator.

Unsupported rule/evidence pairs remain `UNKNOWN`. The current implementation does not infer LLM transport, model response intake, tool dispatch, workflow command semantics, or fixed-context policy from generic symbol names.

## 3. Qualification outcomes

- `SUPPORTED`: the exact source reproduces the narrow proposition declared by the matching rule contract.
- `INSUFFICIENT`: the observation is valid but cannot establish the rule's intended proposition.
- `CONTESTED`: a source-bound counterclaim is recorded against the observation. The counterclaim's semantic validity remains `NOT_ESTABLISHED`; this state does not mean the counterclaim is true.
- `UNKNOWN`: no matching rule-specific semantic validator exists.

A missing observation is not converted into a negative finding. The current result contains only per-observation qualifications; obligation completeness remains outside this milestone.

## 4. Verification and replay

The qualification entry point requires:
- The M7.5.15 observation bundle and its canonical digest.
- The `AssuranceClaim`, `RuleCoveragePlan`, and coverage manifest.
- Independent `verify_rule_derived_manifest` replay.
- The source snapshot manifest, including inventory entry count, inventory digest, and manifest digest.
- The exact repository root used to verify source content hashes and source-line hashes.

For supported evidence kinds, the validator independently replays the AST operation:
- `graph_import`: parse the exact file and confirm the recorded import module at the recorded line.
- `python_syntax_error`: parse the exact file and independently reproduce the syntax error and diagnostic line.
- `scope_exclusion`: validate only the declared-observation shape; it is not accepted as sufficient evidence.

Every obligation ID must occur in the verified rule-derived plan. A source-bound reference is not enough if it is bound to an obligation outside that plan. Qualification results are content-addressed and independently reproducible through `verify_semantic_evidence_qualification(...)`.

Defeater records must identify a target observation and a source path/digest (and line digest when a line is supplied). A source-bound defeater changes an otherwise `SUPPORTED` result to `CONTESTED`; for an already `INSUFFICIENT` result it is retained without overstating the outcome. Counterclaim validity remains `NOT_ESTABLISHED` until a dedicated semantic defeater validator is implemented.

## 5. Public API

Module: `audit_engine/semantic_audit/epistemic/semantic_qualification.py`

- `SemanticQualificationError`
- `semantic_evidence_contract_registry()`
- `qualify_typed_evidence_observations(...)`
- `verify_semantic_evidence_qualification(...)`

The API is exported from `audit_engine.semantic_audit.epistemic`. Qualification is deterministic and replayable; this milestone does not add a persistent qualification ledger.

## 6. Structural, behavioral, and adversarial tests

The dedicated test suite covers:
- Versioned contract registry digest.
- Graph import accepted as a structural fact but rejected as sufficient proof of service non-use or LLM-path absence.
- Exact AST parse failure supporting only the narrow scan-limitation proposition.
- Scope-exclusion observation remaining insufficient without independent inventory replay.
- Unsupported external-model evidence remaining `UNKNOWN`.
- Source-bound defeater resulting in `CONTESTED` while preserving `NOT_ESTABLISHED` counterclaim validity.
- Exact qualification replay and source-drift rejection.
- Source-line digest tampering.
- Observation-bundle digest tampering.
- Rule-obligation binding to the independently verified plan.

## 7. Explicit limitations

M7.5.16 does not:
1. Establish global proposition truth or prove that all applicable rules were selected.
2. Convert `INSUFFICIENT`, `CONTESTED`, or `UNKNOWN` into a pass.
3. Establish graph-service reachability, actual graph computation, or absence from an LLM path.
4. Independently validate the upstream scope-exclusion selection process.
5. Implement semantic validators for LLM transport, external-model intake, tool protocol/dispatch, workflow command semantics, fixed-context allowlists, or other unsupported evidence kinds.
6. Create `EvidenceAssertion` records, mutate epistemic stores, resolve coverage gaps, or upgrade coverage dossiers.
7. Grant `ALLOW`/`DENY`, audit-gate authorization, release approval, or production approval.
8. Provide an external trust anchor or atomic transaction across existing stores.

## 8. CI validation

Workflow: [M7.5.16 semantic qualification](https://github.com/snoopdock/Finite_element_analysis_project/actions/workflows/m7_5_16_semantic_qualification.yml)

Exact-source run, tested revision, dedicated test count, regression count, and compilation result will be recorded after CI completes on the final branch head.
