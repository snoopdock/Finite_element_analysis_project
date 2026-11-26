# AE-32C M7.5.9 — Trusted Rule-Derived Coverage Registry

**Status:** Implemented and exact-source CI validated  
**Branch:** `stage1/section-uuids`  
**Parent:** M7.5.8 — Epistemic Coverage and Unknown-State Assurance  
**Authority:** Derives a finite obligation set from the built-in AE-32C rule contracts; no proposition-truth, closed-world authorization or audit-gate authority

## 1. Problem addressed

M7.5.8 evaluates obligations in a declared manifest but cannot prove that the caller did not omit an obligation. M7.5.9 connects that evaluator's manifest format to the existing versioned AE-32C rule contracts in `audit_engine/semantic_audit/ae32c/rule_contracts.py`.

The rule registry already declares, per rule pattern:
- rule identity and contract version;
- claim polarity;
- required evidence kinds;
- required source/extractor coverage;
- an optional closed-world contract field.

The current built-in rules all have `closed_world: null`. M7.5.9 preserves that state.

## 2. New API

Module: `audit_engine/semantic_audit/epistemic/rule_coverage.py`

- `derive_rule_coverage_plan(claim, source_snapshot_id, graph_snapshot_id, rule_ids)`
- `build_rule_derived_coverage_manifest(claim, plan, assessments=...)`
- `verify_rule_derived_manifest(claim, plan, manifest)`

The immutable `RuleCoveragePlan` binds:
- persisted-claim identity (rechecked by the M7.5.8 evaluator);
- source snapshot and graph snapshot identities;
- built-in registry ID, version and SHA-256;
- selected rule IDs and resolved claim polarities;
- the complete expected obligation IDs derived from every selected rule's required evidence kinds and required coverage dimensions;
- a canonical plan digest.

Each requirement receives a deterministic ID:
- `rule:<rule-id>:evidence:<evidence-kind>`
- `rule:<rule-id>:coverage:<coverage-requirement>`

Assessments may attach to derived IDs only. Unassessed derived obligations are omitted from the assessed tuple and therefore remain `UNKNOWN` in M7.5.8. A caller cannot shrink the expected set through the builder.

## 3. Registry trust boundary

This tranche uses the repository's built-in `rule_registry()` as a versioned source of requirements. It recalculates and checks the registry digest before deriving obligations, checks the schema and contract version, rejects unknown/ambiguous rule IDs, and rejects malformed or duplicate requirement lists.

This is not cryptographic author authentication, signed release verification or immutable external trust anchoring. A code change to the built-in registry changes its digest and must be reviewed as a source change. CI proves behavior for the checked-out source revision; it does not prove that the selected rule IDs are exhaustive for a particular audit request.

The caller still selects the rule IDs. Consequently, the plan is complete only relative to those selected rules. Automatic rule selection from an authenticated audit request and complete source/extractor inventory reconciliation remain future work.

## 4. Closed-world and polarity constraints

The plan records each selected rule's polarity. It does not convert absence or mixed-polarity rules into positive findings. No built-in closed-world contract is added. The existing finding-ledger behavior continues to return `ABSTAIN` for absence and mixed claims while `closed_world` is null.

Even if a future rule declares a closed-world field, M7.5.9 merely records that declaration; it does not independently authorize negative claims. That requires a separately specified, validated admissibility contract.

## 5. Structural and behavioral tests

The dedicated suite covers:
- deterministic derivation of all evidence-kind and coverage obligations;
- preservation of absence/mixed polarity and current no-closed-world state;
- omitted assessments remaining unassessed against the full derived expected set;
- caller attempts to shrink the expected universe;
- caller attempts to add invented obligations;
- unknown and ambiguous rule rejection;
- duplicate selected rule rejection;
- claim/source snapshot binding;
- registry digest mismatch;
- forged or modified plan fields rejected by recomputing the plan from the pinned built-in registry before construction/verification.

The CI workflow runs M7.5.9 after the M7.5.1–M7.5.8 regression suites and stores its log as an artifact.

## 6. Validation result

Exact-source workflow: [45903996222](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45903996222)

- Validated source revision: `121339f4816eb51df521a73d1a926bfeb7e12af2`
- Runtime: Ubuntu 24.04, Python 3.11
- M7.5.9 dedicated suite: 10 passed
- M7.5.1–M7.5.8 regression suites: 87 passed
- Total: 97 passed
- Epistemic package compilation: passed
- Artifact: `m7-5-epistemic-validation-45903996222-1`
- Artifact ID: `15157530475`
- Artifact SHA-256: `f51dc5b57f16fa2bef5014539eee49797d7ac406fffd44c3e1a588a0f8ee71e9`

The initial M7.5.9 attempts exposed two integration defects: eager AE-32C package initialization imported an optional YAML-dependent investigator when only rule contracts were needed, and the new workflow step contained doubled shell continuations. The package exports were made lazy, the workflow command was corrected, and a later test assertion was aligned with the actual error text. The successful exact-source run above validates the final source revision; failed attempts are not included in the passing counts.

## 7. Remaining limitations

1. Rule selection is caller-supplied; the plan does not prove every applicable rule was selected.
2. Source-unit and extractor candidate inventories are not derived at per-file granularity here. Coverage dimensions are those declared in each rule contract.
3. The built-in registry is versioned and digest-checked but not signed or externally authenticated.
4. Graph snapshot identity is bound into the plan, but the existing M7.5.8 manifest schema has no graph-snapshot field; the plan must be retained alongside the manifest to preserve this binding.
5. The plan does not persist itself to the append-only epistemic ledger.
6. No automatic association of all repository knowledge gaps to rule obligations is added.
7. No deterministic audit-gate consumption, ALLOW/DENY transition, or production approval is introduced.

## 8. Closure implication

M7.5.9 closes the specific gap where a caller could silently omit a required evidence-kind or coverage obligation after selecting a rule. It does not close the larger trust question of whether the selected rule set, source universe, extractor inventory or gap inventory is exhaustive. M7.5 remains open.
