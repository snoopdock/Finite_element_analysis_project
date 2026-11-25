# AE-32C Phase 3 — Rule-Specific Coverage and Finding Provenance

**Status:** Implemented; final push-path validation pending after mixed-claim hardening  
**Production approval:** Not granted  
**Pull-request execution:** Deliberately deferred

## 1. Purpose

Phase 3 adds a versioned rule-coverage registry and a finding ledger. It closes an important gap between a graph snapshot and an audit result: a finding must identify the exact rule contract that emitted it, the exact source snapshot and graph snapshot it used, and the source evidence to which it refers.

This is a provenance and coverage contract. It does **not** prove that a finding's interpretation is semantically correct. A source citation can exist and still fail to entail the statement attached to it. The ledger therefore uses `EVIDENCE_BOUND`, not `SUPPORTED`, for successful structural binding.

## 2. Rule registry

Implementation: `audit_engine/semantic_audit/ae32c/rule_contracts.py`.

The registry is versioned as `ae32c/rule-coverage-registry/v1`. Each declared AE-32A finding rule has:

- a stable rule identifier or explicitly declared dynamic identifier pattern;
- a rule-contract version;
- a claim-polarity classification (`positive`, `absence`, or `mixed`);
- required evidence-kind vocabulary;
- required extractor/source coverage;
- an explicit `closed_world` field.

The registry is content-addressed by `registry_sha256`. Unknown or ambiguous rule identifiers fail closed. Dynamic identifiers are limited to the two declared component-specific patterns; there is no generic fallback contract.

The current registry records `closed_world: null` for every rule. That is intentional. It means the implementation has no rule-specific proof that permits an absence claim to be treated as established.

## 3. Rule-specific coverage checks

For each finding, the binder checks:

1. The rule identifier resolves to exactly one declared contract.
2. Every evidence reference points to a path in the exact source inventory.
3. The path is represented in the graph coverage manifest.
4. The graph coverage source digest matches the source inventory digest.
5. The corresponding `file:<repository-relative-path>` graph node exists.
6. Any line reference is a positive integer.
7. The observed evidence kinds include the rule's required evidence-kind vocabulary.
8. Required source/extractor coverage is satisfied for that rule.

Evidence details are not copied into the ledger. The ledger retains the evidence kind, source path and digest, graph node identifier, optional line number, and a digest of the evidence detail. This keeps the artifact compact while retaining stable references.

## 4. Finding status semantics

The ledger assigns one of three statuses:

| Status | Meaning |
|---|---|
| `EVIDENCE_BOUND` | Required evidence references are structurally bound to this source and graph snapshot, and declared coverage requirements passed. This is **not** semantic entailment or proof of the finding. |
| `INSUFFICIENT_EVIDENCE` | Required evidence is absent, unrecognized, or cannot be bound to the source/graph snapshot. |
| `ABSTAIN` | The rule cannot safely make the claim under current coverage or authority conditions. |

Every absence-polarity and mixed-polarity rule is `ABSTAIN` while its `closed_world` contract is null. This remains true even if the overall graph coverage state is `COMPLETE_WITH_DECLARED_EXCLUSIONS`. A mixed statement that combines an observed fact with an inference from absence cannot be promoted merely because its positive evidence was found. The latter is a source/extractor accounting result, not a query-specific proof of absence.

For a future closed-world contract, a rule will need to state at least: the exact source-unit scope, required extractor and relation types, relevant exclusions, completeness predicates, and the source/graph identities to which the contract applies. The contract must be checked against the current run; merely populating a field must not authorize the claim.

## 5. Finding identity and provenance

Each finding identity is a SHA-256 digest over:

- rule ID and rule-contract version;
- source snapshot ID;
- graph snapshot ID;
- severity, title, statement and limitation;
- canonical bound evidence references;
- the assigned assessment status and reason.

The finding ledger carries the registry digest and both snapshot IDs. Its own digest covers the complete ledger. The graph manifest embeds the ledger and repeats its digest. Graph-manifest verification checks ledger integrity and ensures that the ledger is bound to the same source and graph IDs.

This produces three distinct identity layers:

1. **Source snapshot identity** — exact Git source revision and inventory.
2. **Graph snapshot identity** — derived graph content, builder contract and source coverage.
3. **Finding ledger identity** — rule registry, individual finding assessments, and bound evidence.

A change in rules or finding content changes the finding ledger without falsely changing the underlying graph content identity.

## 6. Authority and non-goals

- The ledger is derived evidence, not canonical repository authority.
- A finding ID is an identity, not a truth certificate.
- Evidence membership and digest correspondence do not establish that a quoted passage entails a claim.
- No LLM output can create a rule, expand its scope, or turn `ABSTAIN` into an accepted result.
- Absence claims remain unauthorized by default.
- No remediation, patch, merge, or production-promotion authority is introduced.

## 7. Validation

The workflow now runs the dedicated rule-contract test module in addition to source- and graph-snapshot tests.

The test suite covers:

- positive finding evidence binding to source, graph and rule IDs;
- absence and mixed findings abstaining without a closed-world contract;
- incomplete coverage preventing an evidence-bound status;
- evidence paths outside the source snapshot;
- unknown rule rejection;
- registry and ledger tamper detection;
- finding identity changing when the graph snapshot changes.

The push-triggered workflow run is the authoritative execution record for this implementation. A successful run validates these tests and the integration path; it does not qualify semantic entailment or closed-world absence rules.

## 8. Validation status

An initial push-path run validated the ledger integration, but subsequent review identified that mixed-polarity findings could be marked `EVIDENCE_BOUND` based on their positive evidence even though their statements also depended on an absence inference. The implementation was tightened: both `absence` and `mixed` claims now require a query-specific closed-world contract; otherwise they must remain `ABSTAIN`. A dedicated regression test covers this condition.

The initial run is therefore not the final acceptance record for this version. The current branch revision must pass the complete source/graph/rule workflow after this hardening. No pull request was opened or tested.

## 9. Remaining work

1. Add a semantic support/evidence-entailment verifier as a separate stage; do not overload structural provenance binding.
2. Define closed-world contracts only for narrowly scoped rules where source and extractor completeness can actually be demonstrated.
3. Add rule-specific tests for every declared contract, including deliberately missing evidence and excluded source units.
4. Bind downstream remediation candidates and verification receipts to the finding-ledger identity.
5. Add freshness-guarded publication so a completed older run cannot replace a newer run's current result.

## 10. Files

- `audit_engine/semantic_audit/ae32c/rule_contracts.py`
- `tools/ae32c_graph_snapshot.py`
- `tests/semantic_graph/test_ae32c_rule_contracts.py`
- `docs/audit-engine/schemas/ae32c-graph-snapshot-manifest-v1.schema.json`
- `.github/workflows/ae32c_source_snapshot_manifest.yml`
