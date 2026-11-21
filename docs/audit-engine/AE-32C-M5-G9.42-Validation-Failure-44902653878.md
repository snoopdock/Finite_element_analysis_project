# AE-32C M5 — G9.42 Validation Failure Review (run 44902653878)

**Disposition:** validation failed; three regression assertions exposed two stale test-contract fixtures. Corrective test changes are committed to `stage1/section-uuids`. M5 remains implemented but unvalidated and is not accepted.

## 1. Run identity and branch provenance

- Workflow: Manual Validation Dispatcher, run [44902653878](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/44902653878)
- Workflow-dispatch ref / workflow-definition commit: `main` / `cecf208419887b70c532b57362e6933ac97f72cb`
- Selected source branch: `stage1/section-uuids`
- Exact tested source SHA (checkout log and report): `e979b17b081d5e0a3cf120b184c7016de6dfd3e1`
- Profile: G9.42; CPython 3.11.18
- Job: `136841617180`
- Artifact: `manual-validation-evidence-44902653878-1`, artifact ID `14706403123`
- Artifact ZIP SHA-256: `f10d5dcf2091311418dc74a29499486c33440e6d94d721d681daa465956e363e`
- Validation report SHA-256: `d5d7b7c86d6bd7238ce438acd3d9b50a9983ef1df703524d76a2e85e6c34bb75`
- Immutable evidence bundle SHA-256: `5e0546da43d5b0c5b8ce7e37d80b90b5c0292400939c8d2f05e7250c3693eb51`

The run's top-level `head_branch` is `main` because the dispatcher workflow itself was manually dispatched from `main`. This is not the source revision tested by G9.42: the log explicitly checks out `stage1/section-uuids`, and the report records the exact target branch and SHA above. No repository write was made to `main`.

## 2. Validation result

| Gate | Result |
|---|---:|
| Validation-engine unit tests | 53 passed |
| Targeted suite | 689 total; 684 passed; 5 skipped; 0 failed |
| Full regression | 3,628 total; 3,612 passed; 13 skipped; 3 failed |
| Detached evidence integrity | Passed |
| Immutable content-addressed evidence bundle | Published and verified |
| Provenance catalog build | Failed closed |
| Independent provenance verification | Failed closed |

The provenance failures are downstream consequences of the validation report having a failed test outcome. The catalog correctly refused to publish a passing verification record for a failed run; this is not treated as an independent catalog defect.

## 3. Root-cause analysis

### 3.1 Legacy graph-tool fake omitted the edge-index property map

Two failures occurred in `tests/semantic_graph/test_gb01_optional_native_backends.py`:

- `test_native_backend_preserves_multiplicity_and_metadata[graph-tool]`
- `test_source_mutations_not_reflected_in_native_data[graph-tool]`

Both failed during `GraphToolAdapter` construction at the access `native.edge_index[native_edge]`. The older `FakeToolGraph` implemented property maps and `add_edge()`, but did not model graph-tool's `Graph.edge_index` map.

This was a test-double defect introduced by the M5 adapter's explicit native-edge-identity mapping, not evidence that the real graph-tool API lacks that property. The official graph-tool 3.9 documentation specifies that `Graph.edge_index` maps each edge descriptor to a unique integer and warns that indices need not be contiguous after edge deletion:
- [Graph API — `edge_index`](https://graph-tool.skewed.de/static/docs/stable/autosummary/graph_tool.Graph.html)
- [Quick start — edge indices and property maps](https://graph-tool.skewed.de/static/docs/stable/quickstart.html)

**Correction:** the legacy fake now exposes an `edge_index` property map and records the allocated edge descriptor/index association in `add_edge()`. Its comment makes the scope explicit: it models the simple contiguous-index case used by this legacy projection test. M5's dedicated graph-tool fake remains responsible for non-contiguous index behavior after removals. This keeps the test double aligned with the API consumed by the adapter without weakening the production mapping contract.

### 3.2 M1 registry test retained a pre-M5 graph-tool expectation

One failure occurred in `tests/semantic_graph/test_m1_adapter_protocol_networkx.py`:

- `test_registry_separates_discovery_from_conformance_and_approval`

The assertion grouped `graph-tool` with `snap` and expected both to report `native_adjacency_implementation == "not_implemented"`. That assertion became stale when M5 added graph-tool native adjacency and the registry correctly moved graph-tool to `implemented_unvalidated`.

**Correction:** the test now asserts graph-tool's M5 state explicitly:
- implementation: `implemented_unvalidated`;
- conformance: `not_run`;
- production approval: `False`.

SNAP remains separately asserted as `not_implemented`. This preserves the important distinction between implementation presence, conformance, and production approval.

## 4. Corrective commits

Both changes were committed to `stage1/section-uuids`:

- `80f72b680b5f9b5e9bb15c1cf739cdd7d39cccd1` — model graph-tool's edge-index property map in the legacy fake backend.
- `7becea4463b9276cbcdd49ad83f12a65d82806b7` — align the M1 registry-state assertion with M5's implemented-but-unvalidated graph-tool state.

No production adapter behavior was relaxed. No test was skipped, xfailed, or weakened to suppress the failures.

## 5. Remaining validation and acceptance

The corrections have **not** been executed by the implementer. No local tests were run. The next G9.42 run must target the latest `stage1/section-uuids` head and establish that:

1. Both legacy graph-tool fake tests pass.
2. The registry test reports graph-tool as `implemented_unvalidated`, with conformance `not_run` and production approval false; SNAP remains `not_implemented`.
3. Targeted and full regression suites pass.
4. Evidence integrity, immutable bundle publication and provenance catalog verification all pass.
5. The report binds to the exact Stage1 source SHA tested.

Even a passing G9.42 run is not sufficient by itself for M5 acceptance. The dedicated graph-tool conda-forge E.8.5/E.8.8 workflow must also pass on the same exact source SHA, with real graph-tool tests executed rather than skipped. Until both evidence chains pass, M5 remains **implemented but unvalidated**.

## 6. Evidence integrity

The artifact's report, JUnit XML, logs, bundle receipt and checksums were inspected. The artifact digest and report/bundle digests above are copied from the downloaded artifact and workflow output. The bundle was created despite the failed test outcome; the provenance catalog correctly refused to classify it as a passed validation.
