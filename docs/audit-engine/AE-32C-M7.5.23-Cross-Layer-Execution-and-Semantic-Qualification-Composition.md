# AE-32C M7.5.23 — Cross-Layer Execution and Semantic-Qualification Composition

**Status:** Implemented and CI-validated  
**Branch:** `stage1/section-uuids`  
**Parent:** M7.5.22 — Qualification-Reconciliation Consumer Inventory and Dependency Boundaries  
**Scope:** deterministic composition of M7.5.14, M7.5.17 and M7.5.21 outputs into an inspectable per-obligation view  
**Authority:** derived inspection artifact only; no epistemic or decision authority

## 1. Purpose

M7.5.14 and M7.5.17 reconcile different things:

- M7.5.14 accounts for source/extractor inventory and extractor execution against rule obligations. It explicitly leaves typed-evidence obligations UNKNOWN because extractor output is not typed semantic evidence.
- M7.5.17 reconciles typed semantic evidence qualifications against evidence obligations. Coverage obligations are NOT_IN_SCOPE in that layer.
- M7.5.21 checks persisted qualification currentness and performs historical semantic replay only after currentness preflight succeeds. A blocked invalidated record is not replayed.

M7.5.23 composes these independently produced assessments by exact obligation ID. It does not merge their meanings into one Boolean status.

## 2. Public API

Module: `audit_engine/semantic_audit/epistemic/obligation_composition.py`

Exported API:
- `ObligationCompositionError`
- `compose_execution_and_semantic_obligations(...)`
- `verify_obligation_composition(...)`

Schema:
`ae32c/execution-semantic-obligation-composition/v1`

Inputs:
1. M7.5.14 execution-obligation reconciliation.
2. Its M7.5.14 ledger-integrity and semantic-replay result.
3. M7.5.17 qualification-obligation reconciliation.
4. M7.5.21 currentness-gated persisted-consumer result.

The composition checks both reconciliation content digests, execution replay binding, qualification consumer record identity, consumer outcome shape, and equality of claim, source snapshot, rule plan, coverage manifest, and exact obligation inventories.

## 3. Per-obligation output

Every row contains two separate fields:

- `execution_assessment`: kind, status, reason, candidate IDs and outcome IDs from M7.5.14.
- `semantic_qualification`: qualification state, disposition, reason and observation IDs from M7.5.17.

There is deliberately no combined PASS/FAIL field.

Examples:
- An extractor coverage obligation may be `EXTRACTOR_EXECUTION_COMPLETE` while its evidence obligation remains `UNKNOWN`.
- A semantic evidence obligation may be `SUPPORTED_WITHIN_CONTRACT` while the execution-side typed-evidence assessment remains `UNKNOWN`.
- A coverage obligation remains `NOT_IN_SCOPE` in the semantic qualification layer; that does not erase its execution assessment.

The two dimensions are intentionally not substitutes for one another.

## 4. Currentness behavior

When M7.5.21 returns `REPLAY_VERIFIED` with `CURRENTNESS_CONFIRMED` and a bound successful semantic replay, semantic dispositions are exposed as `CURRENT_REPLAY_VERIFIED`.

When M7.5.21 returns `BLOCKED_INVALIDATED`, the composition:
- retains the qualification record identity;
- labels semantic qualification as `BLOCKED_INVALIDATED`;
- sets current `disposition` to null;
- optionally retains the prior disposition only under `historical_disposition`;
- does not describe the historical disposition as current.

A currentness preflight alone is insufficient: the M7.5.21 semantic replay result and record identity must also be present and verified.

## 5. Replay and integrity

The composition is deterministic and content-addressed. `verify_obligation_composition(...)` checks the composition digest and recomputes the entire result from the four inputs.

The composition does not create another SQLite ledger. Persistence would introduce a new lifecycle and cross-store consistency contract; that is not required for this inspectable derived view.

## 6. Authority boundaries

The composition explicitly records:
- execution reconciliation replayed;
- qualification reconciliation currently replayed only when M7.5.21 confirms it;
- epistemic evidence acceptance remains false;
- proposition truth, graph completeness, assurance success, audit decision authority, ALLOW/DENY authority, release approval and production approval remain false.

No output from one layer upgrades the status of another. No dossier, coverage manifest, assertion, assurance record, ALLOW/DENY result, release or production approval is created or changed.

## 7. Limitations

1. Inputs are caller-supplied mappings and replay results. Content hashes bind bytes/structures but do not authenticate the caller or the origin of a claimed M7.5.21 result.
2. M7.5.21 consumer identity and operation are caller-declared, not authenticated.
3. The composition is not an atomic cross-database transaction across the execution ledger, qualification ledger, consumer-check ledger, dossier and assurance stores.
4. A successful composition proves only that the supplied artifacts satisfy this composition contract and that their supplied replay results have the required shape and bindings.
5. It does not establish exhaustive rule selection, exhaustive source inventory, semantic evidence acceptance, proposition truth, global graph completeness, assurance success, or audit/production authority.
6. The composition is a deterministic view, not a new adjudicator or a replacement for either source reconciliation.

## 8. Validation

Workflow: [M7.5.23 cross-layer obligation composition](https://github.com/snoopdock/Finite_element_analysis_project/actions/workflows/m7_5_23_obligation_composition.yml)

The workflow checks out the exact triggering revision, compiles the epistemic package, runs M7.5.23 composition tests and the M7.5.14, M7.5.17, M7.5.21 and M7.5.22 regressions, then runs the complete M7.5 suite.

Validation evidence:
- [M7.5.23 workflow run 45968036484](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45968036484) — success on exact tested revision `d1c428218e09611956ab3ee06ab77a62adb7cd90`.
- Dedicated M7.5.23 composition tests: 11 passed.
- M7.5.14 execution-obligation regression: 7 passed.
- M7.5.17 semantic qualification regression: 12 passed.
- M7.5.21 currentness-gated consumer regression: 5 passed.
- M7.5.22 dependency-boundary regression: 5 passed.
- Complete M7.5 regression: 240 passed.
- Python 3.11 compilation: passed.

The workflow checked out the exact triggering revision. The successful run validates the tested composition contract and regression suites; it does not authenticate caller-supplied replay-result mappings or create an atomic transaction across the participating stores.
