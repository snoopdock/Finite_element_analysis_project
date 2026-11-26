**Status:** five-backend G4 behavioral conformance passed in [E.8.5/E.8.8 run 102](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45473007901); corrected Linux source-cost measurement and Windows reparse-point compatibility passed in [G4 run 10](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45473007486). Overall G4 remains **Partial**: these results do not establish an atomic repository-wide snapshot or close the postflight / Windows path-opening mutation windows.  
**Latest source-snapshot cost and Windows compatibility execution:** [run 10](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45473007486), tested SHA `098a87394d972010f04466c540fcf5f43b490f9b`.  
**Latest E.8.5/E.8.8 conformance:** [run 102](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45473007901), tested SHA `098a87394d972010f04466c540fcf5f43b490f9b`.  
**Latest native projection cost execution:** [run 18](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45463552807), tested SHA `da3b2748d43f4303aecd1d09fe6cb79498bc026c`. Its graph-tool timing remained unmeasured after an `Illegal instruction`; the later E.8.5/E.8.8 graph-tool conformance job passed, which is not a replacement for that separate cost measurement.  
**Branch:** `stage1/section-uuids`.  
**Scope:** canonical graph snapshot isolation, source-file identity validation, controlled active-query mutation, fixture-tree side effects, native projection corruption, parity fail-closed behavior, repeated queries, reconstruction and SNAP worker teardown.

## 1. Acceptance boundary

G4 is evaluated against the invariant that `SemanticGraph` remains the canonical semantic authority. A backend projection is a computational snapshot; it does not become an alternate semantic source. For this tranche, a passing test means that a bounded query does not mutate canonical graph data, that nested payloads copied into a projection do not alias later caller mutation, that canonical mutation is detected around a query, and that corrupt or incomplete local native adjacency cannot be silently accepted.

This tranche does **not** close G4. The tests use controlled in-memory graphs and injected failure modes. Repository-file side effects, arbitrary concurrent mutation schedules, and off-neighborhood native-object corruption are not fully qualified here.

## 2. Source inspection before test design

The implementation inspected at the branch baseline included:

- `optional_backend_support.make_projection`: validates node identity, edge endpoint membership and mapping payload types, and deep-copies node/edge attributes and metadata before native projection construction.
- `NetworkXGraphTraversalEngine`: clones its input projection, validates the complete NetworkX node/edge projection during initialization, then reads native local adjacency and checks each returned occurrence against canonical edge identity and payload. It compares canonical graph fingerprints before and after query execution.
- `NativeAdapterGraphTraversalEngine`: validates the complete non-NetworkX projection during initialization, obtains query candidates from the selected native local-adjacency API, validates each returned occurrence, and checks the canonical graph fingerprint before and after traversal and parity verification.
- SciPy maintains CSR/CSC connectivity plus semantic edge-occurrence side channels; igraph and graph-tool retain native edge-occurrence identifiers; SNAP runs behind the isolated worker protocol and maps worker edge IDs back to snapshot occurrence IDs.

The code already contains material G4 controls. The missing evidence was a focused five-backend test matrix covering mutable nested payloads, query-time canonical mutation, corrupted local records, missing local records, repeated execution and reconstruction.

## 3. Added test cases

New module: `tests/semantic_graph/test_m74_snapshot_mutation_integrity.py`.

Each case is parameterized across NetworkX, SciPy, python-igraph, graph-tool and the isolated SNAP worker, with workflow-level backend selection preventing a generic interpreter from misreporting unavailable native libraries as executed tests.

| Test case | Required observation |
|---|---|
| Deep snapshot isolation | Mutating nested canonical node/edge payloads after adapter construction does not rewrite the already-created backend snapshot; a subsequent query against the stale canonical snapshot fails closed. |
| Mutation during native adjacency | A mutation to an unreached canonical node after native adjacency has been read is detected by the graph-wide fingerprint guard before a result is accepted. |
| Corrupted local occurrence | A local edge record whose metadata no longer matches the canonical edge occurrence is rejected. |
| Missing local occurrence | With reference parity enabled, a native adjacency response that omits expected occurrences is rejected rather than returned as a successful traversal. |
| Repeated query and reconstruction | Repeated results are identical; a fresh projection over the unchanged canonical graph reproduces the result; SNAP refuses a query after worker closure instead of falling back silently. |

The fixture intentionally includes nested mutable dictionaries/lists, parallel edge occurrences and a self-loop. It avoids relying on any backend's private index representation.

## 4. Workflow integration

The E.8.5/E.8.8 workflow now runs the dedicated G4 module in each backend environment:
- NetworkX, SciPy and igraph matrix jobs, selected by `AE32C_M74_BACKEND`;
- the dedicated graph-tool environment;
- the isolated SNAP worker job after immutable worker-image identity has been recorded.

The workflow is configured for `workflow_dispatch` and for pushes to `stage1/section-uuids` that touch `tests/semantic_graph/**` or the workflow itself. Therefore, committing the test and workflow changes should initiate the native backend matrix automatically. The source SHA in the resulting run must be recorded and checked; the workflow being triggered is not itself a pass.

## 5. Known residual limits — do not overstate G4

1. **Repository-file non-mutation:** this test module operates on synthetic in-memory graphs. It does not open or write repository files. The existing E.8.8 repository fixture has its own source-read and no-side-effect checks, but that evidence does not by itself establish every repository operation's mutation boundary.
2. **Concurrent schedules:** the tests inject a deterministic mutation during a native adjacency call and verify the post-query fingerprint guard. They do not exhaust thread interleavings, mutation-and-restoration between fingerprint checks, or all lifecycle races.
3. **Mutable exported native objects:** adapter exports expose backend-native objects. The current engines perform full projection validation at construction and validate the local adjacency records used by a query; they do not re-enumerate the entire native graph before every bounded query. Consequently, corruption confined to a disconnected or unvisited native region may not be detected by a query that never touches that region. A future policy must decide whether to restrict mutable export access, provide defensive views/copies, or explicitly pay for full projection revalidation. Do not claim global immutability or universal detection of off-path native mutation from this tranche.
4. **SNAP lifecycle:** the tests verify fail-closed behavior after worker closure and successful reconstruction through a new adapter. They do not replace the dedicated live Docker timeout/termination and container-removal suite.

## 6. Evidence and decision status

At the implementation commit, execution was pending. The exact-source run has now completed successfully; its verified record follows in Section 7. The run is interpreted within the residual scope below:
- exact Stage1 source SHA and attempt;
- all five G4 backend jobs executing the new module (not skipped);
- per-backend test totals, failures and skips;
- full E.8.5/E.8.8 jobs and aggregate summary, because G4 is inserted into that existing matrix.

G4 remains **Partial / insufficient evidence** until the five partitions complete and the remaining residual limits are addressed or explicitly bounded by the contract. All 20 task/backend suitability outcomes remain `Insufficient evidence`. No backend ranking or automatic selection follows. `production_approval=false` remains invariant.


## 7. Exact-source G4 matrix execution — 2026-11-24

**Workflow:** [45413494767](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45413494767), attempt 1, push-triggered, completed with conclusion `success`.  
**Tested source:** `stage1/section-uuids` at `7447a6b6327b2f310012088767df8251577f6cb1`. Every backend job logged this same `AE32C_SOURCE_REVISION`.

| Backend | Job ID | G4 pytest result |
|---|---:|---:|
| NetworkX | 138513333211 | 5 passed, 20 skipped |
| SciPy | 138513333115 | 5 passed, 20 skipped |
| python-igraph | 138513333610 | 5 passed, 20 skipped |
| graph-tool | 138513333134 | 5 passed, 20 skipped |
| SNAP isolated worker | 138513332413 | 5 passed, 20 skipped |

The 20 skips in each job are the other four backend partitions excluded by `AE32C_M74_BACKEND`; the selected backend's five parameterized G4 cases executed in each environment. Across the five selected environments, all 25 intended backend-specific test executions passed, with no G4 test failure or error. The SNAP job supplied worker image ID `sha256:033de68b84778a7f67de0492e9fe558ff4bed3fbc26b5235a249875ddd88ccd8`; its post-close query assertion passed as part of the SNAP G4 tests.

All five E.8.5/E.8.8 backend jobs and aggregate summary job `138514348900` also concluded `success`. The run's E.8.5 and E.8.8 reports both recorded `status=passed` for each backend, with E.8.5 14/14 and E.8.8 43/43 parity-verified queries and zero query/parity failures. The five uploaded evidence artifacts are:

| Artifact | ID | ZIP size | Actions SHA-256 |
|---|---:|---:|---|
| NetworkX | 14931650153 | 2,769 bytes | `c46c44ed9f8b9e5cb045e37973829d98440f3eb3ad1e2e41549da0181bc72a35` |
| SciPy | 14931365165 | 2,928 bytes | `12c37b9562a9f2d2298562f30e492b53f9f5ca9a1aa0ad86d7e171ae37201c51` |
| igraph | 14930975424 | 2,746 bytes | `151ba1888095f028fa505f2e9dde7b135b1a7447edca97734c76da9c6fc08585` |
| graph-tool | 14929461149 | 2,845 bytes | `e5184c365174a7ca7120382eaf143c62b57cc65b878ffa33b140bea8e0f4f251` |
| SNAP worker | 14932195241 | 3,428 bytes | `413ec55b6f8c9b6ed8f3253086a8190ef4dd24682201029b7658bfed97a1af83` |

These artifact digests are the GitHub Actions-reported ZIP digests. They do not represent a detached G7 verification of this new run's E.8.5/E.8.8 artifacts; the earlier G7 dossier remains bound to run 45395352748 and its exact historical source.

**G4 interpretation:** the new focused five-backend test tranche passes. This does not close G4. The suite establishes the tested snapshot/query behaviors, but it does not establish global immutability or detection of arbitrary off-neighborhood corruption in mutable native exports. Repository-file no-side-effect behavior and broader concurrency/lifecycle limits also remain. Maintain G4 as Partial and leave all 20 task/backend suitability outcomes at Insufficient evidence. `production_approval=false` remains invariant.

## 8. G4 continuation — complete projection preflight/postflight (implementation pending execution)

The next implementation tranche changes the query integrity boundary for all five backends:

- **Before traversal:** re-enumerate the complete native node and edge-occurrence projection and compare it with the canonical `SemanticGraph`.
- **After traversal and reference-parity work:** repeat the complete projection audit before accepting the result.
- **NetworkX:** rerun full node/edge/occurrence verification at each boundary, including context-adjacency operations.
- **SciPy, igraph and graph-tool:** remove the construction-only validation shortcut. Each query re-enumerates native nodes and all native edge occurrences, while the actual traversal continues to use CSR/CSC, incident-edge IDs or graph-tool edge iterators.
- **SNAP:** add an explicit fresh worker-audit operation so a query does not rely on the adapter's prior audit cache; the complete audit is requested at both boundaries.

The test module now adds:
1. direct off-neighborhood native-projection corruption before a bounded query (NetworkX, SciPy, igraph and graph-tool); SNAP uses a deliberately corrupted fresh audit response because its worker graph is intentionally not exported into the host;
2. off-neighborhood mutation after local adjacency but before query completion, checked by postflight;
3. a SNAP-specific assertion that exactly two fresh `audit` RPCs bracket one query.

These checks target the former blind spot: a query rooted at A must reject a corrupted C-to-C self-loop even though C is outside A's one-hop result.

**Cost and limits:** complete validation adds O(V+E) work before and after each bounded traversal. SNAP additionally incurs two full audit RPCs per query. This is a deliberate integrity/performance tradeoff, not a free strengthening; subsequent task-workload and operational evidence must quantify it. The checks do not establish immutability, prevent an attacker or concurrent writer from mutating and restoring state entirely between observations, or close a race after the final postflight. Repository-file side-effect coverage remains separate.

**Status at this record:** implementation and tests prepared; exact-source five-backend execution pending. G4 remains Partial until the new matrix passes and remaining concurrency/repository-side-effect limits are either tested or explicitly bounded in the contract. All 20 task/backend outcomes remain Insufficient evidence; `production_approval=false`.

## 9. Exact-source five-backend execution of full projection boundary audits — 2026-11-24

**Workflow:** [45423628531](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45423628531), attempt 1, completed `success`.  
**Exact tested source:** `stage1/section-uuids` at `0790019b2d3ce4f4fe9c0f89d58c90eb3a689a9a`.

### 9.1 G4 test matrix

| Backend | Job ID | G4 test result |
|---|---:|---:|
| NetworkX | 138549608093 | 7 passed, 33 expected skips |
| SciPy | 138549607706 | 7 passed, 33 expected skips |
| python-igraph | 138549607991 | 7 passed, 33 expected skips |
| graph-tool | 138549607596 | 7 passed, 33 expected skips |
| SNAP isolated worker | 138549607264 | 8 passed, 32 expected skips |

The four non-SNAP partitions each executed the seven backend-applicable tests. SNAP executed those seven plus the SNAP-specific fresh-audit RPC test. Skips are backend-selection exclusions and the non-SNAP selection of the SNAP-only test. There were no G4 failures or errors. The SNAP-specific test confirmed two fresh `audit` RPCs around one query.

The new tests demonstrate:
- off-neighborhood C-to-C native projection corruption is rejected before a bounded query for NetworkX, SciPy, igraph and graph-tool;
- mutation of an off-neighborhood native record after local adjacency is read is rejected at postflight for those same four backends;
- SNAP refreshes its worker audit at both query boundaries; the host-side test injects a corrupted fresh audit response after local adjacency to exercise the postflight rejection path.

**SNAP limitation:** the worker graph is intentionally opaque to the host. The SNAP fault injection tampers with the fresh audit response, not the internal TNEANet itself. The independent fresh-audit RPC assertion establishes that the cache is not trusted at query boundaries, but it is not a direct in-worker mutation experiment.

### 9.2 Full workflow and existing conformance

All five backend jobs and aggregate summary job `138550687334` completed successfully. The E.8.5 and E.8.8 reports in the run recorded 14/14 and 43/43 parity-verified queries respectively, with zero parity failures. The existing graph-tool and NetworkX protocol tests also passed after their obsolete construction-only/no-full-scan assertions were reconciled with the new G4 query-boundary audit contract.

For SciPy, igraph, graph-tool and SNAP, the report's `native_projection_reads` was:
- E.8.5: 377 reads = 13 initial projection records + 2 × 14 queries × 13 records (5 nodes + 8 edge occurrences);
- E.8.8: 5,829 reads = 67 initial projection records + 2 × 43 queries × 67 records (26 nodes + 41 edge occurrences).

This exactly matches one construction audit plus two complete projection audits per query for the reported fixtures. NetworkX reports full validation node/edge counts through its separate projection-validation metrics. These are record-read counts, not elapsed-time or memory measurements. G5/G6 must still quantify the operational cost under representative audit workloads.

### 9.3 Artifact identities

| Artifact | ID | ZIP size | GitHub Actions SHA-256 |
|---|---:|---:|---|
| NetworkX | 14935062322 | 2,768 bytes | `3a3ff983b163846b69c5d517ad1068b39c2915670d00819359949d1f8e589ce4` |
| SciPy | 14936480568 | 2,927 bytes | `a611775f158cebb9eaa95eb38439014bc72670ce6475c247ebe19d34b2c6143f` |
| python-igraph | 14935392761 | 2,747 bytes | `4a3b75f3af9dcca5c96ca8cf3cf568f13d78bda9f9e55083ed23d6f82dcc6a72` |
| graph-tool | 14935196933 | 2,844 bytes | `65513fff72e6db5c53d3fa13631c6345943e55830ae22b61c44fe761a974dc05` |
| SNAP worker | 14935047472 | 3,436 bytes | `945ee6003330e3265f89770bb5f055c3ac0dcd9747c87653f918b0193b56d3ae` |

These are Actions-reported ZIP digests, not a detached G7 verification of this run. The earlier G7 detached dossier remains bound to run 45395352748 and its historical source.

### 9.4 G4 decision

The off-neighborhood preflight/postflight behavior is now implemented and passed in all five backend partitions, with the SNAP worker caveat stated above. G4 is nevertheless **Partial**, not closed. Remaining work includes repository-file non-mutation coverage, mutation/restoration and broader concurrency/lifecycle schedules, the race after final postflight, direct SNAP in-worker mutation coverage, and G5/G6 characterization of the full-scan cost. All 20 task/backend outcomes remain Insufficient evidence. `production_approval=false`.


## 10. Repository side-effect and concurrent snapshot qualification — implementation and execution

The next G4 tranche adds `tests/semantic_graph/test_m74_repository_side_effects.py` and runs it in every existing E.8.5/E.8.8 backend environment.

### 10.1 Repository-file side effects

The test copies the established AE-32C repository fixture into an isolated temporary directory and records the relative path set, SHA-256 digest of every regular file, and permission mode. It then constructs `RepositoryEvidenceTools` and exercises bounded repository search, symbol search, source-file reading, and graph-neighbor querying. After explicit backend teardown, the complete file-state map must be byte-identical to the initial map. This detects content modification, file creation/deletion, and permission-mode changes within the fixture tree.

This is a test of the evidence-tool operations and selected backend against the fixture. It does not prove that arbitrary operating-system side effects outside the fixture root are impossible; the report must not generalize it to a sandbox guarantee.

### 10.2 Snapshot consistency under external source mutation

A second test constructs the repository evidence snapshot, then performs an external same-size edit to an indexed source file. Concurrent bounded reads are issued through the already-constructed tool instance. They must continue returning the original indexed content and source digest, demonstrating that read operations use the captured in-memory source snapshot rather than reopening a mutable path during each query. The test restores the fixture file in a `finally` block and checks the original bytes.

This establishes per-instance snapshot pinning for the tested file/read path. It does not establish an atomic point-in-time snapshot across every repository file during initial manifest construction; that stronger claim would require a repository-wide snapshot primitive or a second complete manifest validation with a defined race model.

### 10.3 SNAP close/query lifecycle race

The SNAP-specific test holds the adapter's request lock while a query thread is queued, closes the worker, then releases the lock. The queued query must fail closed with `snap_worker_process_not_running`; it must not report a successful traversal after teardown. This tests the serialized worker lifecycle boundary, not every possible process crash, timeout, simultaneous caller, or container-removal interleaving. The existing Docker lifecycle suite remains independently required.

### 10.4 Acceptance and residual limits

The new test module is inserted into all five backend jobs (NetworkX, SciPy, igraph, graph-tool, and SNAP). Exact-source execution is recorded in Sections 11 and 13. A passing run supports the narrow claims above only.

The following remain outside this tranche and must not be silently marked closed: mutation followed by restoration entirely between integrity observations; mutation after final postflight; atomicity of the initial repository-wide source snapshot; direct mutation of the opaque SNAP TNEANet inside the worker; and G5/G6 characterization of full-projection validation cost. G4 remains Partial until these are either addressed or explicitly bounded in the acceptance contract. All 20 task/backend suitability outcomes remain Insufficient evidence and `production_approval=false`.


## 11. Exact-source repository side-effect and lifecycle test execution — 2026-11-24

**Workflow:** [45431740022](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45431740022), attempt 1, completed `success`.  
**Workflow event commit:** `1680d9119315a2a3a42707831e6d1635582d69cc`.  
**Exact checked-out source recorded by the jobs:** `4bf6dcc20812043fc2e048ecbbdacd6d7495350f`.

All five backend jobs and aggregate summary completed successfully. The G4 repository side-effect/snapshot-race test step passed in NetworkX, SciPy, igraph, graph-tool and SNAP. The pre-existing G4 snapshot/mutation test step also passed in all five environments. The SNAP-specific close-versus-queued-query lifecycle test passed as part of its repository side-effect test step.

This run executed the repository immutability, post-construction same-size source mutation/snapshot-pinning, and SNAP queued-query teardown tests. It predates the second-pass manifest validation and its new mutation-during-loading test; those changes require the subsequent exact-source run and are not covered by this run.

## 12. Second-pass manifest validation — implementation and exact-source execution

The content index is now followed by `_validate_loaded_source_snapshot()`, which re-reads every included source file and compares its size-bound SHA-256 to the original audit manifest. This rejects a same-size edit injected immediately after the first content read, before the graph is built and accepted. The new test `test_g4_same_size_edit_during_snapshot_loading_is_rejected` injects that schedule and asserts the structured error code `source_changed_during_index`.

The second pass narrows the construction race but is not an atomic filesystem snapshot. An ABA mutation restored before the second pass remains undetectable, and a mutation after validation does not retroactively alter the already captured in-memory source snapshot. The exact-source workflow run recorded in Section 13 passed this test in all five backend environments. The added full read also has a cost that must be measured; no runtime or memory claim is made here.


## 13. Exact-source second-pass manifest and G4 repository qualification — 2026-11-24

**Workflow:** [45432310272](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45432310272), attempt 1, completed `success`.  
**Workflow event commit:** `5e9724896c62564345cd877d5903e9e5e0a14138`.  
**Exact checked-out source:** `5e9724896c62564345cd877d5903e9e5e0a14138` in all five backend jobs.

All five backend jobs and aggregate summary job `138581810523` completed successfully. The relevant G4 test results were:

| Backend | Existing G4 snapshot/mutation tests | Repository side-effect/snapshot/lifecycle tests |
|---|---:|---:|
| NetworkX | 7 passed, 33 expected skips | 3 passed, 9 expected skips |
| SciPy | 7 passed, 33 expected skips | 3 passed, 9 expected skips |
| python-igraph | 7 passed, 33 expected skips | 3 passed, 9 expected skips |
| graph-tool | 7 passed, 33 expected skips | 3 passed, 9 expected skips |
| SNAP isolated worker | 8 passed, 32 expected skips | 4 passed, 8 expected skips |

The skips are backend-selection exclusions and the SNAP-only lifecycle case on non-SNAP jobs. The SNAP partition executed the additional worker close/query race test. The new same-size mutation-during-loading test passed in every backend job; it constructs the evidence tool with the reference backend so the failure is isolated to source snapshot validation rather than native graph availability.

The run also passed the pre-existing task-level acceptance, synthetic E.8.5 and repository-backed E.8.8 conformance stages in all five environments. The aggregate workflow conclusion was `success`. All five jobs recorded the same exact checked-out source SHA.

**Interpretation:** the tested evidence operations left the isolated fixture tree's file bytes, path set and permission modes unchanged; concurrent reads remained bound to the constructed source snapshot after an external same-size edit; a same-size edit injected after first content read was rejected by the second manifest pass; and the SNAP query queued behind worker teardown failed closed. These are bounded test results, not proof of universal filesystem immutability, atomic repository-wide snapshots, or all possible concurrent schedules.

**G4 remains Partial.** Outstanding limits include ABA mutation/restoration between observations, changes after the final manifest or query postflight check, direct in-worker SNAP TNEANet mutation, and cost characterization of the extra source-manifest pass and complete native projection scans. No task/backend suitability status is promoted and `production_approval=false` remains unchanged.


## 14. G4 deterministic race and workflow provenance corrections — 2026-11-24

Two follow-up commits address the workflow and test-harness defects identified during the G4 re-examination.

**Workflow commit:** [1bb448e](https://github.com/snoopdock/Finite_element_analysis_project/commit/1bb448e326ec8d6e9ebabd85d6bbca2625193568).  
**Test commit:** [66cbc5d](https://github.com/snoopdock/Finite_element_analysis_project/commit/66cbc5dc654c2c09dfaf6f2c83d99516725eadcd).  
**Branch:** `stage1/section-uuids`.

### 14.1 Exact source checkout

All three backend jobs now use `ref: ${{ github.sha }}` rather than resolving the moving branch name at job execution time. The source-recording step compares `git rev-parse HEAD` with `GITHUB_SHA` and exits with an error on mismatch. This prevents a delayed matrix job from silently testing a newer branch head than the event that triggered it.

The workflow path filter now includes `audit_engine/semantic_audit/ae32b/evidence_tools.py`, which contains the second-pass source-manifest validation used by the G4 repository snapshot tests. Missing all conformance report files now causes artifact upload to fail (`if-no-files-found: error`); this setting does not, by itself, validate every individual report's JSON schema or status field.

### 14.2 Backend selector validation

The repository side-effect test module now fails immediately when `AE32C_M74_BACKEND` is set to a value outside the five registered backend names. A typo can no longer make all parameterized backend cases skip while leaving a green pytest exit code. The selected backend is still the only backend executed in each job; other backend partitions are expected skips.

### 14.3 Deterministic SNAP close/query race

The former test signalled that the query thread had started, but did not establish that it had reached the lock acquisition. It now wraps the adapter's existing re-entrant request lock with an observing proxy. The main thread holds the underlying lock, starts the query, and waits for the query thread's actual acquisition attempt to be signalled before calling `close()`. Only then is the lock released. The assertion remains that the queued query fails closed with `snap_worker_process_not_running` and does not increment the successful-query count.

This removes the previous scheduling ambiguity for the specific tested interleaving. It is not an exhaustive proof of every worker shutdown race.

The post-construction external-edit test was also renamed to state its actual schedule: the file is changed after the evidence snapshot is constructed and before concurrent reads begin. It demonstrates snapshot-pinned reads under that schedule; it does not claim that the external mutation occurred during an active query.

### 14.4 Exact-source workflow run

**Run:** [45453260519](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45453260519), run number 92, push event.  
**Head SHA:** `66cbc5dc654c2c09dfaf6f2c83d99516725eadcd`.  
**State at the time of this dossier update:** NetworkX, SciPy, igraph and graph-tool jobs completed successfully; SNAP isolated-worker job was still executing its task-level acceptance step. All four completed jobs logged a checked-out source SHA equal to the run head SHA. Their G4 test steps passed:
- NetworkX: snapshot/mutation 7 passed, 33 skipped; repository side-effect 3 passed, 9 skipped.
- SciPy: snapshot/mutation 7 passed, 33 skipped; repository side-effect 3 passed, 9 skipped.
- python-igraph: snapshot/mutation 7 passed, 33 skipped; repository side-effect 3 passed, 9 skipped.
- graph-tool: snapshot/mutation 7 passed, 33 skipped; repository side-effect 3 passed, 9 skipped.

The skips are the other backend partitions excluded by the selected-backend environment variable. The SNAP G4 partition and final workflow aggregate are intentionally not marked passed in this interim record; they require the run's final result.

The earlier run [45453257165](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45453257165), triggered by the workflow-only commit, was cancelled by the configured `cancel-in-progress: true` when the test commit triggered run 92. This is expected latest-commit behavior, not a test failure.

The repository's `main` branch was checked after these commits and remained at `ee4e4b769221d331b1d2726301349cd0c217ab03`. No change was made to `main`.

**G4 interpretation:** these corrections strengthen test determinism and CI source provenance. They do not make the source snapshot atomic, detect an ABA mutation restored between observations, establish full repository-wide filesystem immutability, or close the remaining concurrency and native-backend limits. Keep G4 Partial and preserve all 20 task/backend suitability outcomes as Insufficient evidence; `production_approval=false` remains invariant.


## 15. Final exact-source execution of deterministic G4 corrections — 2026-11-24

**Workflow:** [45453260519](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45453260519), run number 92, attempt 1, completed with conclusion `success`.  
**Event:** push to `stage1/section-uuids`.  
**Exact tested source SHA:** `66cbc5dc654c2c09dfaf6f2c83d99516725eadcd`.

All five backend jobs logged a checked-out source SHA equal to the event SHA. The explicit checkout assertion passed in every job. All five backend jobs, the aggregate E.8.5/E.8.8 summary job, and all evidence-upload steps completed successfully.

### 15.1 G4 results

| Backend | Snapshot/mutation integrity | Repository side-effect and lifecycle |
|---|---:|---:|
| NetworkX | 7 passed, 33 expected skips | 3 passed, 9 expected skips |
| SciPy | 7 passed, 33 expected skips | 3 passed, 9 expected skips |
| python-igraph | 7 passed, 33 expected skips | 3 passed, 9 expected skips |
| graph-tool | 7 passed, 33 expected skips | 3 passed, 9 expected skips |
| SNAP isolated worker | 8 passed, 32 expected skips | 4 passed, 8 expected skips |

The four non-SNAP partitions execute seven selected-backend snapshot/mutation cases and three repository-side-effect cases. SNAP executes the additional SNAP-specific fresh-audit and close/query lifecycle cases. The skipped cases are the other backend partitions excluded by backend selection, plus SNAP-only tests in non-SNAP jobs. There were no G4 failures or errors.

The SNAP close/query test passed with the instrumented request lock. Its worker image build, adapter protocol/restriction tests, live Docker timeout/cleanup tests, repository backend teardown test, E.8.5 synthetic conformance and E.8.8 repository-backed conformance also passed.

### 15.2 Full conformance and artifacts

All five E.8.5/E.8.8 backend jobs and the aggregate summary concluded `success`. Each backend uploaded its expected E.8.5 and E.8.8 JSON reports; no artifact-upload step failed. The job logs show report status `passed` and zero query failures for the tested conformance outputs. The artifact identities reported by GitHub Actions are:

| Backend artifact | Artifact ID | ZIP size | Actions SHA-256 |
|---|---:|---:|---|
| NetworkX | 14947779116 | 2,767 bytes | `39e3975f49bcfd3e00035e1895f3fa6aa3152d75acc26c215597ef93bea1b6fc` |
| SciPy | 14947354400 | 2,926 bytes | `307a69957889d04eaaf3cad8e49334d4d479f2fa77ea74d9b8f6313d228593d1` |
| python-igraph | 14947784105 | 2,746 bytes | `9905253d9e64175136431c1bc16ae836e4e3a80900694fd0742f7b25d8a402d3` |
| graph-tool | 14947324522 | 2,844 bytes | `33b9cd4124fada4a7fd3e34dfafec69f73c716fb6ee0912d445b15252f8ce6eb` |
| SNAP isolated worker | 14948997478 | 3,433 bytes | `19534555d2ec07668f2e92f77a7b707642f8e218104a123fa69f1d17c6064dbb` |

These digests are the Actions-reported ZIP digests. They are recorded as artifact identities, not represented as independent detached verification of the report contents.

### 15.3 Final interpretation

The two implementation commits and their exact-source run establish the following limited results:

1. The five backend jobs checked out the triggering commit, not a later moving branch head.
2. Changes to the second-pass source-manifest implementation now trigger the workflow through the path filter.
3. Invalid backend selectors fail rather than silently skipping every backend partition.
4. The SNAP close/query test waits for a real lock-acquisition attempt before closing the worker.
5. All five selected backend partitions passed the G4 snapshot/mutation and repository-side-effect/lifecycle test modules.
6. The existing E.8.5/E.8.8 conformance jobs and artifact uploads also passed on the same exact source.

This is stronger evidence for the tested cases, but it does **not** close G4. The test tree-state helper covers regular-file path membership, content hashes and permission modes; it does not prove absence of side effects outside the fixture or cover every filesystem metadata category. The post-construction external-edit test does not inject mutation during an active query. The second-pass manifest check is not an atomic repository-wide snapshot and can miss an ABA change restored between observations. Broader mutation/restoration schedules, changes after final validation, direct in-worker SNAP graph mutation and G5/G6 cost characterization remain open or explicitly bounded.

**Decision:** G4 remains **Partial**. Do not promote any of the 20 task/backend suitability outcomes from `Insufficient evidence`. `production_approval=false` remains unchanged.

**Repository refs after the documentation update:** `stage1/section-uuids` is advanced by the dossier update; `main` remains `ee4e4b769221d331b1d2726301349cd0c217ab03`. No changes were made to `main`.


## 16. Source identity, active-query mutation and expanded tree-state qualification — 2026-11-24

This tranche extends the repository-file qualification from Section 10 and the two-pass source validation described in Section 12. It is tested on exact source SHA `7ce60f233fc98042c832d24140ecc5e52aefff99`.

### 16.1 Descriptor-bound file identity across snapshot passes

The source reader now returns both file bytes and a descriptor-bound identity signature. The signature records device, inode, file type, permission mode, size, modification time at nanosecond precision where exposed, and change time at nanosecond precision where exposed. The reader compares `fstat` identity before and after each read. The loader stores the first-pass identity for every included non-sensitive manifest entry, including entries that are later excluded from text indexing because they are not UTF-8. The validation pass compares the second identity with the stored first identity as well as checking the manifest SHA-256.

This catches ordinary change-and-restore schedules between the two reads on filesystems that expose the corresponding metadata changes. The new characterization test changes `main.py` after the first descriptor read, waits briefly, restores the original bytes before the validation read, and asserts that construction fails with `source_changed_during_index`. This is materially stronger than content-hash comparison alone: final bytes and size match, but the observed file identity history does not.

The guarantee remains bounded. Metadata precision and semantics vary by filesystem and platform. A filesystem with coarse or synthetic timestamps may conceal some changes. The identity is first captured during content loading, not atomically with the earlier repository manifest scan, so a change-and-restore completed before the first descriptor read is not necessarily detectable. Directory-entry changes between manifest creation and validation are not made atomic by this file-level signature. This remains best-effort mutation detection, not a repository-wide snapshot primitive.

### 16.2 Mutation while a source query is in flight

A new cross-backend test pauses `read_source_file` inside its source-line processing after the handler has entered the active query. While the query is paused, the fixture's `main.py` is changed on disk without changing its byte length. The query is then released and must return the already captured in-memory content and source digest.

This tests a different schedule from Section 10.2: the external edit occurs while the tool invocation is in flight, rather than before concurrent reads are started. It establishes snapshot pinning for this read operation and controlled interleaving. It does not prove that every tool operation, every query phase, or every possible mutation schedule is race-free. The test does not prevent the external writer from changing the fixture; it verifies that the in-flight evidence result remains tied to the constructed source snapshot.

### 16.3 Expanded fixture-tree state

The repository side-effect helper now records:
- regular-file relative paths, SHA-256 content digests and permission modes;
- directory relative paths and permission modes;
- symlink relative paths, permission modes and link targets;
- the presence and type of other filesystem entries encountered by the walk.

The walk does not follow directory symlinks. This improves the previous helper, which captured regular-file paths, bytes and modes but did not represent directories or symlink objects. The no-side-effect assertion therefore covers more of the fixture tree's observable structure.

It still does not cover ownership, timestamps, ACLs, extended attributes, hard-link identity, all device/special-file metadata, effects outside the fixture root, or changes made and restored entirely between observations. It must not be described as proof of universal filesystem immutability or as a process sandbox.

### 16.4 Exact-source workflow run 95

**Run:** [45456154169](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45456154169), run number 95, push event.  
**Head SHA:** `7ce60f233fc98042c832d24140ecc5e52aefff99`.  
**Conclusion:** `success` for all five backend jobs and the aggregate E.8.5/E.8.8 summary. The five backend jobs logged a checked-out source SHA equal to the triggering SHA.

| Backend | Snapshot/mutation integrity | Repository side-effect and lifecycle |
|---|---:|---:|
| NetworkX | 7 passed, 33 expected skips | 6 passed, 13 expected skips |
| SciPy | 7 passed, 33 expected skips | 6 passed, 13 expected skips |
| python-igraph | 7 passed, 33 expected skips | 6 passed, 13 expected skips |
| graph-tool | 7 passed, 33 expected skips | 6 passed, 13 expected skips |
| SNAP isolated worker | 8 passed, 32 expected skips | 7 passed, 12 expected skips |

The non-SNAP jobs execute the selected backend's three parametrized repository tests, the tree-state characterization, the reference-backend ABA test and the snapshot-loading mutation test. SNAP additionally executes the worker close/query lifecycle test. Skips are the other backend partitions and the SNAP-only test where not applicable. There were no test failures.

All five E.8.5/E.8.8 backend jobs and the aggregate summary passed. The run uploaded these five artifacts:

| Backend artifact | Artifact ID | ZIP size | Actions SHA-256 |
|---|---:|---:|---|
| graph-tool | 14951531060 | 2,843 bytes | `231c19083be3bc420420f5144a2271d7d88719d90ec83fda1c16957a1082e286` |
| SciPy | 14950986262 | 2,927 bytes | `243ba941da14f2a9a3c98e643fa494842699a11590d3d15f61dce2b3395b8e60` |
| SNAP isolated worker | 14950077618 | 3,433 bytes | `3344fa7c8655ffb711838c4d12cf94e15ca2b3ff066d36c934743dd270797449` |
| NetworkX | 14949903091 | 2,767 bytes | `99f7e64808bfe187e1d47665198942d91566e33389e1a5c1a1065d943171216d` |
| python-igraph | 14949144503 | 2,746 bytes | `2ce37288e46e6edf7ed9c407e01703a4f48380d7d6771d901a52d6cbb6d9cf01` |

These are GitHub Actions-reported artifact ZIP digests, recorded as artifact identities rather than independent detached verification of the JSON payloads.

### 16.5 Updated G4 interpretation and remaining work

This tranche now establishes, for the tested fixture and schedules:

1. file identity is compared across the two source-loading observations, and an ordinary same-size change-and-restore between those observations is rejected;
2. an external same-size edit during an in-flight `read_source_file` invocation does not change the returned snapshot-bound content or digest;
3. the fixture-tree comparison includes regular files, directories, symlinks and entry types, not only regular-file bytes and modes;
4. the five selected backend partitions pass the expanded G4 tests and the existing E.8.5/E.8.8 conformance workflow on one exact source revision.

The following remain open or bounded:
- atomicity of the repository manifest and file-content snapshot as a single point-in-time observation;
- ABA changes completed before the first descriptor identity is captured, and schedules hidden by filesystem metadata semantics;
- mutation after the final native projection postflight observation and before the query result is returned;
- direct mutation of the opaque SNAP TNEANet by modified or compromised worker code remains outside the assurance boundary; Section 17 verifies that the supported protocol exposes no mutation operation and that post-init operations are read-only, but does not inject corruption inside the worker process;
- filesystem side effects outside the fixture root and metadata categories listed as out of scope above;
- G5/G6 characterization of the full-projection validation and second source pass cost.

**Decision:** G4 remains **Partial**. The new checks close specific evidence gaps but do not justify a global immutability or atomic-snapshot claim. Keep all 20 task/backend suitability outcomes at `Insufficient evidence`; keep `production_approval=false`.


## 17. SNAP worker protocol read-only boundary — 2026-11-24

The remaining SNAP-specific G4 question was whether the isolated worker's supported request protocol provides any operation that can mutate its TNEANet after initialization. Inspection of `tools/snap_worker.py` establishes the operation allowlist in `_handle`:

| Operation | State effect |
|---|---|
| `init` | Constructs the TNEANet once and installs the semantic node/edge mappings |
| `audit` | Reads all native nodes and edges into a serialized projection |
| `adjacency` | Reads native incident edge IDs and edge records; updates telemetry counters only |
| `metrics` | Returns telemetry counters |
| `close` | Returns the close acknowledgement; the worker loop exits |

After initialization, the worker rejects any operation outside `audit`, `adjacency`, `metrics` and `close`. In particular, `mutate` is not an accepted protocol operation. The adjacency path uses SNAP's node iterator and incident-edge-ID accessors, then reads edge attributes; it does not call TNEANet mutation methods. The audit path also reads the graph. The host adapter serializes request/response exchanges under its request lock, and the worker processes the JSON-lines stream sequentially.

A new subprocess test, `test_snap_worker_protocol_rejects_unexposed_mutation_operation`, sends a syntactically valid `mutate` request to the real worker script without initializing SNAP. The worker returns `request_schema_invalid`. This is a protocol-boundary test, not a native TNEANet mutation test.

**Why no test-only mutation RPC was added:** exposing an operation that deliberately mutates the worker graph would expand the production protocol solely to test an internal state that the supported interface does not expose. The current assurance model instead treats `tools/snap_worker.py` and the pinned worker image as trusted implementation components, and verifies that their supported post-init operations are read-only. This does not prove that a modified or compromised worker cannot mutate or misreport its internal graph. The host can only validate the projection returned by the worker.

### 17.1 Exact-source execution

**Run:** [45457395602](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45457395602), run number 96, push event.  
**Head SHA:** `315a23ed8c69aab2d1dec69607b64a9eccb9501c`.  
**Conclusion:** all five backend jobs and the aggregate E.8.5/E.8.8 summary succeeded. Each backend job logged the exact triggering source SHA.

The SNAP worker protocol test module reported **6 passed**. The G4 modules retained their run-95 results: SNAP snapshot/mutation **8 passed, 32 expected skips**; SNAP repository-side-effect/lifecycle **7 passed, 12 expected skips**. NetworkX, SciPy, igraph and graph-tool each reported snapshot/mutation **7 passed, 33 expected skips** and repository-side-effect/lifecycle **6 passed, 13 expected skips**. There were no failures.

All five E.8.5/E.8.8 artifacts were uploaded:

| Backend artifact | Artifact ID | ZIP size | Actions SHA-256 |
|---|---:|---:|---|
| NetworkX | 14951312857 | 2,766 bytes | `031e8ca46f63846944488a3b36c3f9f5cdf23b16fff95a31f828f49a293ebace` |
| graph-tool | 14950657277 | 2,842 bytes | `f7dc82a23705ff301c6a774ebf43f3dbbe8077ecce2db85a9adf49e774b1bd8b` |
| SciPy | 14950587208 | 2,924 bytes | `f622931d5c49ac8f0d52bc7826babd8c2886a67c23e45d5b23c4fdaa03d360de` |
| SNAP isolated worker | 14950462483 | 3,432 bytes | `0f549a174ffab17597ed2cbe649aee15f16a5a76b31b8a452fa9d151db892776` |
| python-igraph | 14950353356 | 2,744 bytes | `94ebdd6fbe8af05676b98e02fbb8f0ff541747387275a3be4e8f77c4d0d55d6c` |

These are GitHub Actions-reported ZIP digests, not independent detached verification of artifact contents.

### 17.2 G4 interpretation

The SNAP protocol boundary is now explicitly qualified: no supported post-init request mutates the TNEANet, and the protocol rejects a mutation request. The worker implementation remains trusted code; this is not a proof against malicious or defective worker code. G4 remains **Partial** because atomic repository-wide snapshot semantics, some metadata-hidden ABA schedules, postflight mutation windows, and the measured cost of integrity checks remain unresolved.

The next cost-characterization work must follow the existing M7 policy: measure the operational cost of integrity checks for each backend in its own task-relevant environment, without producing a universal backend ranking or winner. Timing remains diagnostic evidence, not an automatic selection criterion.


## 18. Integrity-audit cost instrumentation — 2026-11-24

This tranche adds diagnostic timing for the full native-projection integrity audits already executed around each traversal query. It changes the M7.1 benchmark harness and its tests; it does not change production traversal or projection-validation code.

### 18.1 Measurement boundary

The benchmark installs an instance-local timing wrapper after the measured engine has been constructed:

- NetworkX: wraps `NetworkXGraphTraversalEngine._verify_projection`.
- SciPy, python-igraph, graph-tool and SNAP: wraps `NativeAdapterGraphTraversalEngine._build_adjacency`.

For each successful measured query, the current implementation is expected to execute exactly two full projection audits: one preflight and one postflight. The harness records every audit duration and the paired sum for each query. It rejects a report if the observed audit count is not exactly twice the measured query-call count.

The existing `engine_construction_ns` remains a combined construction measurement and includes the constructor's initial projection audit. It is not presented as an isolated audit measurement. Query wall-clock observations continue to include integrity audits, canonical fingerprint checks, traversal and result construction. The new audit timings therefore provide a component measurement, not a claim that subtracting the audit time yields a fully isolated traversal runtime.

The wrapper is benchmark-local and installed only on the measured engine instance. No production telemetry or runtime behavior is modified.

### 18.2 Report contract and verification

The M7.1 report schema is advanced to `ae32c/m7-native-backend-benchmark/v2`. Each query now records:
- the exact integrity-audit observation count;
- individual audit durations and their median, p95, minimum, maximum and median absolute deviation;
- paired preflight-plus-postflight duration observations for each measured query call, with the same aggregates.

The independent report verifier reconstructs the expected pairwise sums from the raw audit observations, recomputes timing aggregates, and rejects altered audit counts, samples or aggregates. This makes the timing fields internally checkable after report generation; it does not independently reproduce the wall-clock measurements.

The benchmark test module now asserts the two-audits-per-query invariant and includes rehashed report-forgery tests for audit timing and count.

### 18.3 Exact-source execution

The branch now contains:
- benchmark instrumentation commit `7b10ce11058caf1344da5db2438d7e00fe931825`;
- test commit `50ee7e425e0f7cc72b28f552936359479daa252a`;
- dedicated M7.1 workflow commit `641982f9efb176e81a95ab0676cc3e9ff43be683`;
- report-schema version commit `8fbbc6b73455020eeb1dbda866d58a1bcd5c1e47`.

The workflow's first exact-source push attempt, **Run 45462809897** (run 14; head SHA `8fbbc6b73455020eeb1dbda866d58a1bcd5c1e47`), passed actionlint but failed in source resolution before any backend job ran. The logs show that the `workflow_dispatch` inputs were empty on a `push` event; the resolver consequently rejected the empty requested ref and timing settings. This was a workflow event-context defect, not a benchmark or backend test failure.

The workflow was corrected to use the dispatch inputs when present and otherwise default to `github.ref_name`, five timed repetitions and two warm-ups on push. The corrected workflow was pushed as `da1d8420c24a4ecbd0611abfde0936cb953f051a`. **Run 45463087734**, run number 15, was queued against that exact workflow commit when this dossier update was made; its outcome is not yet claimed. The workflow checks out an immutable resolved source SHA and preserves separate backend runner environments and artifacts. It is the same smoke workload, not the multi-seed/task-specific M7.2 campaign.

### 18.4 Interpretation and limits

The measured audit duration is a diagnostic component of the current integrity strategy on the fixed E.8.5 adversarial fixture. It is not a backend ranking, universal performance comparison, or backend-selection rule. Backend-specific runner and library environments remain part of the evidence; measurements must not be pooled into a universal winner claim.

This tranche does not yet measure:
- the second repository source-validation pass and descriptor-identity checks in `evidence_tools.py`;
- scaling across multiple repository sizes or graph workload classes;
- filesystem I/O, memory allocation, CPU utilization or worker startup as separate components;
- the cost of each individual integrity sub-check inside a full projection audit.

The SNAP audit measurement includes the worker's full projection-audit request and host-side validation. It does not isolate container IPC, serialization, native iteration and host comparison as separate subcomponents.

**Decision:** G4 remains **Partial** pending the exact-source workflow result and broader integrity-cost characterization. No task/backend suitability outcome is promoted; all 20 remain `Insufficient evidence`. `production_approval=false` remains unchanged.


### 18.5 Workflow event-context follow-up

Run 15 successfully resolved a source ref and passed workflow lint, but its five backend jobs still failed before benchmark execution. The backend steps had their own raw `inputs.repeats` and `inputs.warmup` references; on a push event these are empty even when the resolver has valid defaults. Run 16 (`45463180074`, head SHA `b7fa687f31af33b354c6b93e3cad7365ef16d9e9`) repeated that failure mode. The logs show the benchmark CLI rejecting `--repeats ''`; they do not show a benchmark assertion or backend execution failure. The workflow-lint job passed in both runs.

The workflow was then corrected at every backend-step environment reference to default to five repetitions and two warm-ups when dispatch inputs are absent. Push-triggered runs now resolve `github.sha`, not a moving branch name, so the measured source is pinned to the triggering commit. The same workflow revision also adds an explicit NetworkX-job pytest step for `test_m7_native_backend_performance_benchmark.py`, covering the timing contract and report-forgery tests rather than relying only on the benchmark CLI verifier.

The follow-up commits are:
- `463c45bcbb5d2d9d1910b9ea34b42ba70982427b`: propagate timing defaults to every backend job;
- `b7fa687f31af33b354c6b93e3cad7365ef16d9e9`: pin push-triggered source resolution to `github.sha`;
- `da3b2748d43f4303aecd1d09fe6cb79498bc026c`: run the M7 integrity timing contract tests in the workflow.

Run 17 (`45463422308`) was cancelled while queued behind an earlier run when a newer workflow commit arrived. **Run 18 (`45463552807`)** is the current validation attempt, with workflow head SHA `da3b2748d43f4303aecd1d09fe6cb79498bc026c`; it was pending when this section was recorded. No backend timing outcome is inferred from the earlier workflow-input failures. The next status update must inspect Run 18's exact-source checkout, test step, all five benchmark/verification steps and aggregate result.


### 18.6 Exact-source results — Run 18

**Run:** [45463552807](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45463552807)  
**Workflow head and resolved source SHA:** `da3b2748d43f4303aecd1d09fe6cb79498bc026c`  
**Configuration:** five measured calls and two warm-up calls per query; seven query forms; fixed E.8.5 fixture with 5 nodes and 8 edge occurrences.  
**Workflow conclusion:** `failure`, solely because the graph-tool benchmark process terminated with signal-derived exit code 132 (`Illegal instruction`). The lint and source-resolution jobs passed. NetworkX, SciPy, python-igraph and SNAP each completed benchmark generation and independent report verification successfully.

The NetworkX integrity-timing contract test step reported **15 passed in 0.24 s**. All four successful backend reports independently verified seven query outputs and reported `winner_established=false`.

The following are backend-local diagnostic summaries. Each number is the median across the seven per-query medians from this one smoke fixture; it is not a pooled sample or a cross-backend comparison. Audit-pair time is the sum of the preflight and postflight projection-audit observations for a measured query.

| Backend | Library version | Median query wall time | Median paired audit time | Median per-query audit share |
|---|---:|---:|---:|---:|
| NetworkX | 3.6.1 | 758,894 ns | 169,632 ns | 23.2% |
| SciPy | 1.17.1 | 935,180 ns | 550,492 ns | 58.3% |
| python-igraph | 1.0.0 | 1,124,399 ns | 555,059 ns | 48.0% |
| SNAP worker | 6.0.0 | 2,986,278 ns | 1,769,406 ns | 59.3% |
| graph-tool | no report | no measurement | no measurement | no measurement |

The audit-share value is computed per query as paired audit time divided by that query's total measured wall time, then summarized by the median across the seven query forms. These ratios are diagnostic descriptions of this fixed fixture and runner configuration only. The engine-construction measurement still combines projection construction and its constructor-time initial audit. Query wall time includes fingerprint checks, integrity checks, traversal and result construction. The benchmark does not isolate every operation or establish how the shares scale with larger workloads.

**Runner context:** NetworkX, SciPy and SNAP ran on GitHub-hosted Ubuntu x86_64 AWS runner images; python-igraph ran on an Ubuntu x86_64 Azure runner image. Their independent runner instances and library environments are not controlled paired experiments. graph-tool's environment provisioned successfully, but Python terminated with `Illegal instruction` immediately when the benchmark process started. Its failure is not a slow timing, a projection-audit rejection, or a semantic-parity failure. The uploaded graph-tool artifact contains environment and failure logs but no benchmark JSON.

**Report identities (report SHA-256):**
- NetworkX: `0f9cb2a2855645310f1ce9031fb23c0a75cd7b3eaf0d2eb9a98baecb5ac0ea38`
- SciPy: `14ca8e481f20e2c4a712262763b355692f1531f50646a6703736dd6ffda1bbfe`
- python-igraph: `5cd643ef5a13890166441c88770c081f8ebaa856e1662274f0fb849a9370a7fb`
- SNAP: `0e9a50e6d7ffc0c06080b93634d24fd4bb0de53ff433ccd3aa8f490d70efe29f`

**GitHub Actions artifact identities (ZIP digest reported by Actions):**

| Backend | Artifact ID | ZIP size | Actions SHA-256 |
|---|---:|---:|---|
| NetworkX | 14954971013 | 4,140 bytes | `23d7184bde6d8fcdca8bbb68d88bd68aaaf07e126957db6bbcd79550092fdefd` |
| SciPy | 14955060771 | 4,185 bytes | `626b9da358ac95bcd05d6050ac23921e950f0dbafbdfb5e417682f01c8afebfe` |
| python-igraph | 14954890982 | 4,197 bytes | `6bc9671a6086ba41413f71d71734e7243e82430ff9a735932a188cd386066449` |
| SNAP | 14954531740 | 4,884 bytes | `8bc2ffdbaeb912a5860a5d7dd970e5928968f6c94cd263a681bff5c05d5a660a` |
| graph-tool | 14954716297 | 3,159 bytes | `631a6612d6037c46b8b5c613a1fd0e8269017d4c36b2f054ca6834ef048cbb9e` |

The ZIP digests are the values reported by the Actions upload step. They identify the uploaded archives and are not detached signatures or independent proof of their contents.

**Interpretation:** this run confirms that the new instrumentation and report-verification contract operate for four backend configurations on the fixed fixture. It provides an initial indication of how much of each measured query was spent inside the two full projection audits on those particular runner environments. It does not establish comparative backend suitability, universal audit overhead, scaling behavior, or a performance winner. The graph-tool execution remains uncharacterized because of the runner process fault.

**G4 decision:** remains **Partial**. Source-validation-pass timing, multi-size workload scaling, finer SNAP audit subcomponent timing, and broader runner repeatability remain open. Keep all 20 task/backend suitability outcomes at `Insufficient evidence`; keep `production_approval=false`.


## 19. Preliminary source-snapshot timing — superseded

The initial source-only benchmark was [run 5](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45465670711), tested SHA `2322efae96a2c4f2a310236d9522b294cbaaeaef`. It passed its then-current report contract, but a later technical review found that the per-file read-counting callback was active inside the timed content-load and validation methods. The callback performed a Python wrapper call and counter updates for every file read, so the reported phase durations included instrumentation overhead. In addition, the three-sample nearest-rank p95 was necessarily the maximum observation and did not provide a useful tail estimate.

Accordingly, the earlier values (6.858 s audit, 95.87 ms content load, 91.03 ms validation, 7.051 s pipeline) are **superseded and must not be used as the production phase-cost baseline**. The earlier artifact and report hashes remain historical identifiers only. The corrected methodology and replacement measurements are recorded in Section 20.

## 20. Technical review and corrected source-snapshot cost — 2026-11-24

### 20.1 Review findings and corrections

The review used the production implementation, G4 tests, workflow definitions and current Python/GitHub Actions/benchmarking documentation.

1. **Per-file timing instrumentation contaminated the earlier measurements.** The v2 benchmark wrapped `_read_snapshot_file_with_identity` during timed content loading and validation. The wrapper's Python callback and counter updates were included in those phase durations. Schema v3 times the production audit/load/validation methods without that wrapper. It performs a separate, unmeasured read-accounting replay after the timed pipeline.
2. **The old p95 label overstated what three observations could show.** The v3 report no longer emits a p95 for this small sample. It records ten observations, median, minimum, maximum and median absolute deviation. This remains a repeated single-process diagnostic, not a multi-process pyperf distribution. pyperf's methodology uses multiple worker processes and multiple values per process; this benchmark does not claim equivalent statistical coverage.
3. **The verifier did not fully reconstruct source-read accounting.** V2 compared the manifest hash and total included count/bytes, but did not independently derive the expected non-sensitive source-file count and byte total from the reconstructed manifest. V3 recomputes those values and rejects a rehashed report that fabricates consistent sample counters.
4. **The verifier did not bind the report to the workflow's expected commit.** V3 checks the report's source and runner revisions against the exact triggering SHA supplied by the workflow. The report digest remains an unkeyed integrity checksum, not a digital signature or proof of runner identity.
5. **The Windows timestamp semantics needed a code correction.** POSIX `st_ctime_ns` is metadata-change time. On Windows, Python 3.11 exposes creation time through `st_ctime_ns`; Python 3.12+ provides `st_birthtime_ns`. The identity helper now prefers `st_birthtime_ns` when available and falls back to `st_ctime_ns` on older Windows runtimes. A unit test covers both branches. Neither Windows field is a metadata-change clock.
6. **The portable Windows path fallback is not equivalent to POSIX descriptor-relative traversal.** Python documents that `dir_fd` support is unavailable on Windows. The fallback resolves and checks path containment before opening, which validates ordinary/static path cases but cannot provide the same protection against a concurrent junction/reparse-point replacement as the POSIX directory-descriptor path. The new Windows job tests ordinary snapshot/mutation behavior; it does not close this adversarial TOCTOU boundary.
7. **The branch-only cost workflow had a misleading manual trigger.** GitHub documents that `workflow_dispatch` only receives events when the workflow file is on the default branch. Because this workflow is intentionally confined to `stage1/section-uuids` and `main` remains untouched, the nonfunctional manual trigger was removed. The workflow is push-triggered by declared path filters.

Relevant external references and audit impact:

- [Python `os.stat_result` timestamp documentation](https://docs.python.org/3/library/os.html#os.stat_result.st_ctime_ns): distinguishes Windows creation-time semantics from POSIX metadata-change time and documents `st_birthtime_ns`.
- [Python `os.supports_dir_fd` documentation](https://docs.python.org/3/library/os.html#os.supports_dir_fd): states that `dir_fd` parameters currently work on Unix platforms and not Windows; this is why the Windows fallback cannot claim the same descriptor-relative race resistance.
- [Python `time.perf_counter_ns`](https://docs.python.org/3/library/time.html#time.perf_counter_ns): supports the high-resolution elapsed-time measurement used by the benchmark.
- [pyperf benchmark methodology](https://pyperf.readthedocs.io/en/latest/run_benchmark.html): supports the limitation statement about single-process repeated measurements versus multi-process benchmarking.
- [GitHub Actions `workflow_dispatch` event](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_dispatch): confirms why the branch-only manual trigger was removed.

### 20.2 Corrected benchmark contract

Schema: `ae32c/m7-g4-source-snapshot-cost/v3`.

- Two warm-up iterations and ten measured iterations.
- Complete `audit_repository` call measured separately from first content load and second descriptor-identity/hash validation.
- Per-file accounting replay occurs outside the timed interval.
- Both source passes must account for the same non-sensitive manifest file count and byte total.
- The verifier reconstructs expected source count/bytes from the current manifest, checks timing observations and aggregates, and validates pipeline-time decomposition.
- Expected source and runner revisions are checked against report provenance.
- Graph construction and traversal-backend initialization are excluded.

### 20.3 Exact-source execution and measurements

**Run:** [45473007486](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45473007486)  
**Source SHA:** `098a87394d972010f04466c540fcf5f43b490f9b`  
**Workflow conclusion:** success; both Linux measurement and Windows compatibility jobs passed.  
**Linux contract tests:** 12 passed.  
**Windows G4 tests:** 27 passed, 46 skipped under the explicit NetworkX-only configuration. The Windows-only directory-junction escape test passed.  
**Benchmark:** two warm-ups, ten measured samples.  
**Report verification:** passed in the run step and again in a separate workflow step.

The audited repository snapshot contained 1,857 non-sensitive source files totaling 9,520,835 bytes. Both source passes accounted for exactly 1,857 reads and 9,520,835 bytes. No non-UTF-8 files were skipped. The manifest SHA-256 was `bb72bdae59c90f19a6b5f7cfcdf1a808019666c4612bd134b958cf7bab69e2b1`.

| Timed phase | Median | Minimum | Maximum | MAD |
|---|---:|---:|---:|---:|
| Complete `audit_repository` call | 4.589 s | 4.437 s | 4.844 s | 69.83 ms |
| First content-load pass | 42.84 ms | 42.73 ms | 43.18 ms | 0.037 ms |
| Second source-validation pass | 39.17 ms | 39.06 ms | 39.53 ms | 0.072 ms |
| Source-snapshot pipeline total | 4.671 s | 4.520 s | 4.927 s | 69.98 ms |

The second pass corresponds to approximately 21.10 microseconds per file and 0.839% of the measured pipeline median. This is the validation phase's share of the observed pipeline, **not** an incremental overhead measured against a no-validation baseline. The complete audit phase includes inventory, manifest construction and static analysis; it is not a pure directory-walk measurement.

Environment: Python 3.11.18, Linux 7.0.0-1014-aws, x86_64. The ten observations are from one runner and one repository revision, in one process. Other hosted-runner executions produced materially different medians; these results must not be pooled or interpreted as a universal cost estimate. They do not establish a scaling curve or cross-host variance.

The paired Windows job ran on Windows Server 2022 with Python 3.11.9. It exercised the portable fallback and passed 27 tests with 46 skips. The Windows unit test exercised the `st_birthtime_ns` selection branch and its older-runtime `st_ctime_ns` fallback; the Python 3.11 Windows runner itself used the fallback.

### 20.4 Report and artifact identities

- Manifest SHA-256: `bb72bdae59c90f19a6b5f7cfcdf1a808019666c4612bd134b958cf7bab69e2b1`
- Report SHA-256: `8af85c25ef02558de2a965b76b3778648f43bfd651f07b2fed9a8f946b490e08`
- Actions artifact ID: `14958063284`
- Artifact name: `m7-4-g4-source-snapshot-cost-45473007486-1`
- Artifact size: 2,771 bytes
- Actions-reported ZIP SHA-256: `d1c0f170e5c2e99f831fb9b4f2eb81f997438fc737500cbd8374d3206aa8e2b4`

The downloaded ZIP's SHA-256 was independently recomputed and matched the Actions upload digest. The JSON report's canonical SHA-256 was independently recomputed and matched `report_sha256`. The in-workflow verifier returned `verified` twice with source and runner revision equal to the exact run SHA.

### 20.5 Interpretation

This closes the **measurement-method correction**, adds Windows compatibility coverage for the supported Python 3.11 fallback, prefers `st_birthtime_ns` where available, and rejects static Windows reparse points in the path fallback. It does not establish an atomic filesystem snapshot, close ABA schedules, protect the Windows path fallback against a concurrent reparse-point replacement between component inspection and open, or measure a no-validation counterfactual. G4 remains Partial.

## 21. E.8.5 / E.8.8 and five-backend G4 regression — 2026-11-24

**Run:** [45473007901](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45473007901)  
**Exact source SHA:** `098a87394d972010f04466c540fcf5f43b490f9b`  
**Workflow conclusion:** success, including the aggregate E.8.5/E.8.8 summary job.

All five backend jobs passed: NetworkX, SciPy, python-igraph, graph-tool and the isolated SNAP worker. For every backend:

- E.8.5 synthetic conformance: 14/14 queries succeeded and were reference-parity verified; zero query or parity failures.
- E.8.8 repository-backed conformance: 43/43 queries succeeded and were reference-parity verified; zero query or parity failures.
- M7.4 task-level acceptance: 21 passed, 84 expected skips.
- G4 snapshot/mutation tests: NetworkX, SciPy, python-igraph and graph-tool each reported 7 passed / 33 expected skips; SNAP reported 8 passed / 32 expected skips.
- G4 repository side-effect/lifecycle tests: NetworkX, SciPy, python-igraph and graph-tool each reported 7 passed / 14 expected skips; SNAP reported 8 passed / 13 expected skips. The additional Linux skip is the Windows-only junction test.

The SNAP worker additionally passed six protocol/container-restriction tests, the live Docker timeout/container-cleanup test, two repository-backend resource-teardown tests, its G4 tests and both E.8.5/E.8.8 workloads. The E.8.5 report records an enforced 120-second request timeout; E.8.8 records an enforced 30-second request timeout. Provider credentials were not passed to the worker.

Five artifacts were uploaded. Each downloaded archive's SHA-256 was independently recomputed and matched the corresponding Actions upload digest; every contained E.8.5/E.8.8 report records status `passed`, source SHA `098a87394d972010f04466c540fcf5f43b490f9b`, 14/14 E.8.5 queries and 43/43 E.8.8 queries.

| Backend | Artifact ID | Size | Independently matched ZIP SHA-256 |
|---|---:|---:|---|
| graph-tool | 14956094000 | 2,846 bytes | `a14b0c980cbb3b48ac4543f8991bd90788db2b87549a76d1cfcaf282aad48e84` |
| NetworkX | 14957483338 | 2,770 bytes | `405d08ecf84037da757b1a810d619b184d00d71009817537cd0a89686b073f16` |
| SciPy | 14956708544 | 2,929 bytes | `16814cdcea9fde5460170d3cb8baecd348d674fb3551ebf14cf78c855e6e0076` |
| python-igraph | 14959140093 | 2,749 bytes | `644996cad98dec296072f5adc2d04168ff7bddbb333847ffd436dfebca96e9fd` |
| SNAP isolated worker | 14956883659 | 3,429 bytes | `f9353cf1f20951e236d1ea37c1918d2e071e86d248c01e677308c532caddf0f9` |

**Evidence-integrity qualification:** archive hashes and embedded source/run identities were independently checked. The full detached semantic dossier verifier remains bound to the earlier run `45395352748`; this newer artifact set has not yet been processed by a separately parameterized detached dossier. Do not treat archive-hash verification alone as equivalent to the G7 semantic dossier.

## 22. Cross-thread milestone continuity

This G4 work preserves, but does not advance or close, the other project tracks:

- **Graph-native audit engine (001):** the canonical semantic graph remains authoritative; native backends remain replaceable computational projections. No backend is declared a universal winner.
- **Pluggable LLM integration (003):** the LLM remains outside the control plane; schema-valid model output is not itself evidence or authorization.
- **Quantifying remediation decisions (004):** hard constraints remain non-compensatory; scoring preferences cannot override a failed hard constraint or independently authorize a patch.
- **Formal solver portfolio (005):** solver outcomes remain typed and require independent validation against the exact formal instance; no solver/backend result is treated as a Boolean proof by itself.
- **Self-examination and termination (006):** audit and verification work remains bounded, with explicit termination and late-result validity requirements; no unbounded agentic loop is introduced.

M7.2 and M7.3 remain accepted at their previously recorded scope. M7.4 remains a qualification/assessment phase, not a backend-selection decision. All 20 task/backend suitability outcomes remain `Insufficient evidence`; `production_approval=false`.

**G4 decision:** **Partial**. Atomicity, postflight mutation, Windows reparse-point TOCTOU after component inspection, out-of-root side effects and representative task-scale integrity-cost characterization remain open.

## 23. Next G4 technical tranche

The next correctness work should characterize the final native-projection postflight-to-return window and the Windows component-inspection-to-open window. Neither is closed by the current tests. Repository-wide atomicity still requires either an immutable filesystem snapshot or a stronger external coordination contract; a second validation pass alone cannot establish a single point-in-time multi-file view.

The existing `tools/gb05_native_backend_performance_benchmark.py` already times NetworkX `_verify_projection` and native-adapter `_build_adjacency` preflight/postflight audits and records projection reads. It should be extended with task-relevant workload families and backend-local reporting rather than replaced by a duplicate timer or converted into a universal backend ranking. The current five-node smoke result is not a representative workload characterization.

G4 remains **Partial** until those boundaries and out-of-root side effects are addressed with explicit tests and evidence.

## 24. Latest G4 repository-side-effect and snapshot-race execution — 2026-11-25

**Five-backend workflow:** [run 45600944022](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45600944022), attempt 1  
**Exact tested source:** `ed33bf68c49fd41506d5d7917fbdc77bf8e544e7`  
**Detached G7 verification of this E.8.5/E.8.8 artifact set:** [run 45601831710](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45601831710), success

All five backend jobs and the aggregate summary succeeded. Each backend reported 21 passed / 84 expected skips for the M7.4 task acceptance module. The G4 snapshot/mutation module reported 7 passed / 33 expected backend-selection skips for NetworkX, SciPy, python-igraph and graph-tool; SNAP reported 8 passed / 32 expected skips. The G4 repository side-effect/snapshot-race module reported 7 passed / 14 expected skips for the four in-process backends and 8 passed / 13 expected skips for SNAP. The extra Linux skip is the Windows-only directory-junction test.

SNAP additionally passed six worker protocol/container-restriction tests, the live Docker timeout/container-cleanup test, and two repository-backend resource-teardown tests. E.8.5 and E.8.8 passed with 14/14 and 43/43 parity-verified queries respectively, zero query/parity failures, and the expected native adjacency telemetry. The later detached G7 workflow independently verified the five original E.8.5/E.8.8 archives for this exact source/run; see [the run-specific dossier](AE-32C-M7.4-Detached-E85-E88-Evidence-Dossier-45600944022.md).

### 24.1 What the repository-side-effect tests establish

The test tranche exercises the following bounded cases:

- Repository-backed evidence operations preserve file bytes and permission modes within the copied repository fixture.
- A same-size external disk edit after construction does not replace the already-pinned in-memory source snapshot returned by repository evidence queries.
- A same-size disk edit during an active read query does not rewrite the content/hash pair used by that query.
- An ordinary change-and-restore schedule between the initial load and second validation pass is detected through descriptor-bound identity observations.
- A same-size source edit during initial loading is rejected by the second manifest validation.
- A SNAP query waiting for the worker request lock when close occurs fails closed after the worker is stopped; it does not report a successful query against the closed worker.

The tree-state helper explicitly does not cover ownership, timestamps, ACLs, extended attributes, hard-link identity or external filesystem effects outside the copied root. The Windows-only junction test is separately covered by the paired Windows compatibility job in run 45473007486; it verifies rejection of a static junction/reparse-point escape, not a concurrent replacement race.

### 24.2 Remaining G4 boundaries

These results do not prove an atomic repository-wide point-in-time snapshot. The initial manifest, content-load pass and second validation pass can still observe a sequence of filesystem states; a second pass narrows and detects tested races but does not make the whole multi-file view atomic.

The Windows portable fallback inspects path components before opening them. A concurrent junction/reparse-point replacement between inspection and open remains a TOCTOU boundary because the fallback is not equivalent to POSIX descriptor-relative traversal. The current tests also do not establish that every possible out-of-root effect, filesystem metadata change, hard-link alias, or concurrent mutation-and-restoration schedule is detected. A successful postflight scan does not prove that the projection cannot be changed after the scan but before the result is returned.

### 24.3 Decision

This execution closes the exact-source test requirement for the current repository-side-effect/snapshot-race tranche and strengthens G4 evidence. It does **not** close G4. Atomic snapshot semantics, the Windows path-opening race, full external side-effect coverage, the postflight-to-return race and broader mutation schedules remain unresolved. G4 stays **Partial**.

The same run does not turn any task/backend pair into a suitability approval. All 20 outcomes remain **Insufficient evidence**; no backend ranking, automatic selection, scientific approval or production approval follows. `production_approval=false`.


## 25. Windows handle-bound containment against junction replacement — 2026-11-25

**Implementation source:** `0b37e79c9942e483cea770fc96138c4f185753e1`  
**G4 workflow:** [run 45602554567](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45602554567), success  
**Windows job:** `139165068194`, success  
**Five-backend regression:** [run 45602554671](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45602554671), all five backends and aggregate summary success

### 25.1 Implementation

The Windows fallback now binds the source read to actual open handles instead of relying only on a prior component check:

1. Open the repository root with `CreateFileW`, `FILE_FLAG_BACKUP_SEMANTICS` and `FILE_FLAG_OPEN_REPARSE_POINT`; reject a reparse-point root or a non-directory handle.
2. Open the candidate file with `CreateFileW` and `FILE_FLAG_OPEN_REPARSE_POINT`; reject a final-component reparse point using `GetFileInformationByHandleEx(FileAttributeTagInfo)`.
3. Obtain normalized final paths from both handles using `GetFinalPathNameByHandleW`. Prefer `VOLUME_NAME_GUID`; retry with the DOS volume-name form if GUID naming is unavailable. Compare the opened file's final path to the already-open root handle's final path, using a component-boundary prefix check. Reject if the actual opened object resolves outside the root.
4. Transfer the same file handle to a CRT descriptor and read from that handle. Compare descriptor identity before and after the read and enforce the expected size.

This closes the specific race where a directory component is inspected as an ordinary directory, then replaced by a junction before the file open. The check is performed against the final opened object, not a path string resolved earlier.

### 25.2 Adversarial Windows test and result

The new Windows-only test deliberately creates a normal in-root directory and file, allows the component `lstat` checks to complete, renames that directory, and installs a junction at the same path pointing to an outside directory immediately before the candidate file is opened. The test requires the handle-bound final-path check to reject the outside target.

The first attempt, run `45602327903`, failed before exercising the helper because the test fixture's two payloads had different lengths (25 bytes versus 23 bytes). This was a test-fixture defect, not evidence for or against the handle check. The fixture was corrected to use an equal-length outside payload. The subsequent exact-source Windows job in run `45602554567` passed: **28 passed, 46 expected skips in 1.27 seconds**, on Windows Server 2022 with Python 3.11.9 for the test step. The new junction-replacement test passed together with the existing static junction, source-snapshot and repository-side-effect tests.

The same source passed the Linux source-snapshot cost characterization job and all five E.8.5/E.8.8 backend jobs in run `45602554671`. Each backend reported 21 M7.4 task-acceptance passes, 14/14 E.8.5 parity-verified queries and 43/43 E.8.8 parity-verified queries, with zero query/parity failures. The SNAP job also passed its worker protocol, live Docker timeout/cleanup, task acceptance, G4 and resource-teardown tests. The exact five-backend artifact set was detached-verified in [run `45602963647`](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45602963647), with the machine-readable result committed at `evidence/m74-e85-e88-run-45602554671/verified-dossier.json` and the full interpretation in [the run-specific dossier](AE-32C-M7.4-Detached-E85-E88-Evidence-Dossier-45602554671.md).

### 25.3 Assurance boundary

**The tested Windows junction-swap-to-outside race is now rejected by a handle-bound final-path check.** This is stronger than the prior lstat/resolve/open sequence, but it is not a universal proof for every Windows filesystem namespace or every reparse-point type. The current test covers a local NTFS-style directory junction on the hosted Windows Server 2022 runner; it does not exhaust mount points, network shares, all volume aliases, hard-link aliasing, root replacement schedules or all permission configurations. If final-path resolution cannot be established, the implementation fails closed rather than falling back to an unchecked path read.

This does not create an atomic repository-wide snapshot. It also does not close every filesystem metadata/external-side-effect boundary, every mutation-and-restoration schedule, or the native-projection postflight-to-return window. A validated file handle secures the identity and containment of that individual read; it does not prove that all files in a multi-file repository view existed in one common instant.

**G4 status:** improved; Windows component-inspection-to-open escape is closed for the tested junction-replacement schedule. G4 remains **Partial** pending a declared/implemented repository-wide snapshot consistency contract, broader filesystem namespace and side-effect coverage, and native projection concurrency/postflight closure. All 20 task/backend suitability outcomes remain Insufficient evidence; `production_approval=false`.


## 26. Research-informed boundary: path confinement is not repository snapshot atomicity — 2026-11-26

The current reader now has two distinct containment mechanisms: POSIX descriptor-relative component traversal with no-follow handling, and Windows handle-bound final-path validation with reparse-point rejection. The Windows implementation is stronger than a path-only check because it validates the actual opened object. Neither mechanism establishes that all files in a multi-file repository view were observed at one common instant.

### 26.1 Relevant platform primitives

Linux `openat2(2)` provides a single kernel path-resolution operation relative to a directory descriptor. Its `RESOLVE_BENEATH` constraint rejects resolution that escapes the supplied directory; `RESOLVE_NO_SYMLINKS` rejects symbolic links in every path component; and `RESOLVE_NO_MAGICLINKS` explicitly rejects magic-link resolution. The manual page notes that `RESOLVE_BENEATH` currently also disables magic links but recommends specifying `RESOLVE_NO_MAGICLINKS` explicitly because that behavior may change. `openat2` has been available since Linux 5.6. These flags can strengthen or simplify the Linux path-confinement implementation, but they do not create an atomic snapshot across multiple independent file opens. Reference: [Linux openat2(2) manual](https://man7.org/linux/man-pages/man2/openat2.2.html).

Windows `CreateFileW` with `FILE_FLAG_OPEN_REPARSE_POINT` opens the reparse point itself instead of following normal reparse-point processing. That is the relevant primitive behind the current handle-bound check; the final opened handle still has to be inspected and checked against the held root handle. It is not a repository-wide snapshot primitive. Reference: [Microsoft CreateFileW documentation](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew).

### 26.2 Snapshot consistency decision

Do not treat stronger pathname resolution as a substitute for snapshot consistency. The next G4 design decision should separate two input classes:

1. **Committed source state:** resolve the exact Git commit/tree identity first and read the immutable Git object graph (or a detached worktree pinned to that commit). The graph and its coverage denominator must bind to that same source identity.
2. **Dirty working-tree state:** capture a private immutable staging snapshot or use a filesystem snapshot/copy-on-write facility where available. If a point-in-time snapshot cannot be obtained, the reader must report a bounded, non-atomic observation or abstain; a before/after manifest alone must not be described as atomic.

A multi-pass manifest remains useful for detecting tested changes, but it cannot rule out a mutation-and-restoration schedule between observations or prove that every file came from one simultaneous filesystem state.

### 26.3 Remaining adversarial acceptance work

The next G4 tranche should test and specify:

- Multi-file writes during enumeration and during content loading, including a writer that changes one file while another is being read.
- Mutation-and-restoration (ABA) schedules that restore file bytes, size and timestamps before postflight.
- Directory rename, symlink, junction, mount-point and hard-link alias schedules on the platforms where those objects are supported.
- Mutation of the canonical graph after the final projection audit but before the query result is returned.
- A positive consistency test proving that an accepted result corresponds to one immutable source snapshot, not merely two matching observations.
- Fail-closed behavior when a stable snapshot cannot be established.

**G4 remains Partial.** The Linux and Windows path-confinement primitives support safe individual file opens under tested conditions; neither closes the repository-wide atomicity, full filesystem-side-effect, mutation/restoration or postflight-to-return gaps. No M7.4 task/backend suitability outcome is upgraded by this research note.
