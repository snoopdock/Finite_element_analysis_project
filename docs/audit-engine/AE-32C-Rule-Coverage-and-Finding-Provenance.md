# AE-32C Phase 3 — Rule-Specific Coverage and Finding Provenance

**Status:** Implemented and push-path validated on `stage1/section-uuids`  
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

Every absence-polarity rule is `ABSTAIN` while its `closed_world` contract is null. This remains true even if the overall graph coverage state is `COMPLETE_WITH_DECLARED_EXCLUSIONS`. The latter is a source/extractor accounting result, not a query-specific proof of absence.

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
- absence findings abstaining without a closed-world contract;
- incomplete coverage preventing an evidence-bound status;
- evidence paths outside the source snapshot;
- unknown rule rejection;
- registry and ledger tamper detection;
- finding identity changing when the graph snapshot changes.

The push-triggered workflow run is the authoritative execution record for this implementation. A successful run validates these tests and the integration path; it does not qualify semantic entailment or closed-world absence rules.

## 8. Push-path validation record

**Workflow run:** [45634781802](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45634781802)  
**Tested source revision:** `f07015e875de16e9f6f36d6600c2ff3281c05e96`  
**Workflow conclusion:** success  
**Artifact:** [ae32c-source-graph-snapshot-45634781802-1](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45634781802/artifacts/15032113508)  
**Artifact ID:** `15032113508`  
**Artifact size:** 291,569 bytes  
**GitHub-reported ZIP SHA-256:** `b2e34c152ace042ea3a0c1db4555c1d4bbd84b6140ff571fc156d5194fdfc700`

The workflow passed 8 source-snapshot tests, 10 graph-snapshot tests, and 8 rule-contract tests. Source identity was verified before and after graph projection. Graph-manifest verification also checked the embedded finding ledger and the top-level rule-registry digest reference.

Observed run data:

- source snapshot ID: `dfe802dcd4acde315eb917327ab0c97716dce02c667e39f39b781ce7b112e6e8`;
- source inventory: 1,947 Git tree entries;
- graph snapshot ID: `ac7263a66b20fc1e619361084aebaed6389ebdf97162ea5874361d5c1b43fdb5`;
- graph content SHA-256: `f82ae3a7b4b5f1e339fd447b295b2c97e1de3bc4f559abd9eca933ce9216c43b`;
- graph size: 11,281 nodes and 40,157 edges;
- source coverage: 1,879 represented, 68 declared exclusions, zero unaccounted;
- finding ledger: 9 findings;
- assessment statuses: 6 `EVIDENCE_BOUND`, 3 `ABSTAIN`;
- rule registry SHA-256: `446d1b2c294b09e6921cc6be422bb1f4d8cc97821f43835715a81ea45d97de79`;
- finding ledger SHA-256: `e79b7f0223247c5c59afca1c96ce7b20340a5e3d9d9aea167d78f0af21937148`.

The three abstentions include absence-polarity rules for which no closed-world contract has been established. The `EVIDENCE_BOUND` status records structural provenance only; it is not a semantic entailment verdict.

This is a push-event validation. No pull request was opened or tested, as explicitly deferred.

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
