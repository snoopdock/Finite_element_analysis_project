# AE-32C M1 — NetworkX Validation Record

**Status:** Accepted for the NetworkX adapter protocol and tested repository-backed path  
**Validation date:** 2026-11-21  
**Target branch:** `stage1/section-uuids`  
**Source commit:** `fb3f26e0600c5abe894fb54c9b0cecefed2476f2`  
**Workflow:** [G9.42 Manual Validation Dispatcher — run 44892453883](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/44892453883)

---

## 1. Validation identity

The workflow was dispatched through the central validation engine on 2026-11-21. Although the dispatcher workflow itself is hosted on `main`, its job explicitly checked out the requested source branch and recorded the source SHA below. The validation target was not the dispatcher commit.

| Field | Recorded value |
|---|---|
| Requested source branch | `stage1/section-uuids` |
| Checked-out source SHA | `fb3f26e0600c5abe894fb54c9b0cecefed2476f2` |
| Central validation engine SHA | `cecf208419887b70c532b57362e6933ac97f72cb` |
| Profile | `G9.42` |
| Regression mode | `profile` |
| Python | `3.11.18` |
| Workflow run / attempt | `44892453883` / `1` |
| Final report status | `passed` |

The workflow's `head_branch=main` and `head_sha=cecf208...` identify the dispatcher workflow source. The validation receipt and catalog entry separately bind the actual tested source to `stage1/section-uuids` at `fb3f26e...`.

## 2. Test results

| Test stage | Result |
|---|---:|
| Validation-engine unit tests | 53 passed |
| G9.42 targeted test selection | 671 passed, 6 skipped |
| Full repository regression | 3,602 passed, 14 skipped |
| Final evidence verification | Passed |
| Provenance catalog construction and independent verification | Passed |

The focused M1 module, `tests/semantic_graph/test_m1_adapter_protocol_networkx.py`, ran in the full regression suite. All **18 test cases** passed. These cover typed records and occurrence identity, outgoing/incoming/bidirectional semantics, self-loop handling, isolated/unknown nodes, payload isolation, observational telemetry, no full native-edge enumeration, no query-time Python reference-adjacency rebuild, typed adapter dispatch, mapping corruption, mutation detection and separation of capability declaration from acceptance.

The targeted profile also ran the E.8.5 native-backend and E.8.8 NetworkX repository-backend test modules. The NetworkX native conformance test passed. The repository tests invoked `run_repository_conformance(..., "networkx")` and asserted a passing report, source-hash follow-through, backend parity telemetry and zero context bypasses.

### Skips and limitations

The six targeted skips and fourteen regression skips are recorded in the workflow artifact. The native conformance skips include igraph, graph-tool and SNAP because their native libraries were not installed in that Python 3.11 interpreter. Other skips concern environment-specific compatibility or external tools. These skips do not represent NetworkX failures and do not qualify those other backends as accepted.

The dedicated `.github/workflows/e85-native-graph-backend-conformance.yml` workflow was **not separately dispatched**. Its NetworkX-focused protocol tests and repository-runner assertions were nevertheless executed under G9.42 on the exact source SHA. The standalone workflow's additional direct report artifact is therefore not part of this validation record.

## 3. Evidence integrity

| Evidence item | SHA-256 / identifier |
|---|---|
| Validation report SHA-256 | `8b83d4075f9eebce1ab239061f29037179276bd167022c1d047d263ef8189f69` |
| Content-addressed evidence bundle SHA-256 | `89f13925e5ff0f73098e26fcf634eaa73118be3376ff0df103731bf263823b8a` |
| Uploaded artifact ZIP SHA-256 | `d46ed3fee8dd99197a73cb9c4c2e965397592a5d3ba6946876d48bc193ea4b5d` |
| Artifact ID | `14702747095` |
| Artifact name | `manual-validation-evidence-44892453883-1` |
| Catalog status | `passed` |
| Catalog targeted-test count | `677` |

The evidence artifact contains the report, its checksum, targeted and regression logs/XML, validation-engine log, content-addressed bundle receipt and provenance catalog. The catalog entry binds branch, source SHA, profile, run ID, report digest and bundle digest.

## 4. Acceptance decision

**M1 is accepted for the NetworkX adapter contract and the tested repository-backed NetworkX path.**

The decision is limited to the exact source commit above and the Python 3.11 environment used by the run. It does not establish acceptance for SciPy, python-igraph, graph-tool or SNAP. It also does not establish performance superiority or live LLM graph-tool utilization.

M2 may now proceed to complete the remaining NetworkX context/workflow tool routing through backend-independent graph queries. M2 changes require a new exact-commit validation; this record does not validate subsequent commits.

## 5. References

- [M1 adapter protocol and conformance contract](AE-32C-M1-Adapter-Protocol-and-Conformance-Contract.md)
- [Graph backend compatibility and utilization roadmap](AE-32C-Graph-Backend-Compatibility-and-Utilization-Roadmap.md)
- [G9.42 workflow run 44892453883](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/44892453883)
- Source commit: https://github.com/snoopdock/Finite_element_analysis_project/commit/fb3f26e0600c5abe894fb54c9b0cecefed2476f2
