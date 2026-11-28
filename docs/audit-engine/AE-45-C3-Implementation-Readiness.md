# AE-45 — C3 implementation readiness and execution boundary

**Branch:** `stage1/section-uuids`  
**Baseline:** `600e1239791e6c2944a8c9edad64f08c3e04d683`  
**Status:** C0–C2 validated; provider-free C3 execution-contract layer committed; live C3 executor not implemented; no provider call authorized or executed.

## 1. Verified state

The AE-32D implementation record establishes:

- A deterministic condition report and sanitized task projection are implemented and validated.
- B performs retrieval-only graph assistance, embeds the A report, and preserves A's decision.
- C0 validates manual authorization and the B report's graph/source provenance without importing a provider factory or accessing credentials.
- C1 builds a bounded investigator request and explicitly labels A/B as machine-generated context, not ground truth.
- C2 reconstructs and verifies the exact B graph snapshot.
- The latest recorded full C0–C2 validation is GitHub Actions run [46036244213](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/46036244213).
- The registered request profile is Cloudflare `@cf/qwen/qwen3.8-27b`. The recorded upper bounds are 11 model rounds, 12 tool calls, 30,720 total tokens, 900 seconds, and USD 0.50.

These are protocol and execution-readiness results. They are not A/B/C diagnostic-accuracy results.

## 2. C3 boundary

C3 is the actual bounded AE-32C investigation. It is distinct from C0 preflight, C1 request packaging, and C2 graph reconstruction.

C3 must not execute unless a separately supplied authorization envelope is valid and bound to the exact case, source commit, task-contract digest, B-report digest, graph fingerprint, prompt source, tool catalog, and cost estimator. A/B outputs remain investigative context and must not be treated as ground truth.

No live provider request was made during this audit. The prior execution decision was to defer C3 until the provider/model and budget are explicitly authorized. This note does not grant that authorization.

## 3. Integration incompatibilities to resolve before dispatch

### 3.1 Token-budget mismatch

The AE-45 request contract permits at most 30,720 total tokens. The existing AE-32C helper `build_live_investigation_limits()` constructs `InvestigationLimits(max_total_tokens=180_000)`.

C3 must not use that helper unchanged. The C3 adapter must construct the investigator limits from the validated authorization/request budget and enforce the 30,720 ceiling at the investigator boundary. A smaller authorization value must remain smaller; no default may widen it.

### 3.2 Request-to-investigator binding

The first integration inspection found that C1 set `require_complete_investigation_context=true` while emitting an empty `required_context_paths` list and potentially a null `required_context_target`. The actual `RepositoryInvestigator` constructor rejects this combination. This has now been corrected in C1: it selects a trace target from the declared Python source paths and supplies the other declared-scope paths as required context paths. The C request schema now requires a nonempty target, at least one context path, and mandatory context-trace prefetch. The C1 test suite asserts the exact contract and rejects a one-file scope that cannot satisfy it.

C3 now independently checks the receiving-constructor preconditions. In particular, validate that:

- every required source path belongs to the exact reconstructed source snapshot;
- the required graph target is a declared source path and resolves to a valid target in the reconstructed graph;
- relation types and direction are supported by the selected graph backend;
- the required context target and paths are nonempty, distinct, safe, within the declared scope, and passed with context-trace prefetch enabled;
- the investigator's graph fingerprint and source manifest match the C2-verified values.

C3 must reject unknown, omitted, duplicated, or mismatched requirements rather than silently weaken the investigation contract.

### 3.3 Source snapshot selection

C3 must derive its source/fixture root from the trusted case record and exact pinned source identity. It must not accept an arbitrary caller-supplied repository path or silently use the current branch checkout when the request names another source commit.

### 3.4 Dispatch and failure containment

The provider factory and credential-bearing environment may be accessed only after all offline checks pass and explicit manual dispatch confirmation is present. Timeouts, cost exhaustion, provider errors, malformed responses, incomplete evidence, and stale snapshot identity must remain explicit non-success outcomes. A late response must not be committed after cancellation or snapshot invalidation.

## 4. C3 contract implementation delivered

The provider-free C3 contract is implemented in `tools/ae32d_c3_execution_contract.py`. C1 context-contract compatibility has also been corrected. The contract:

- reconstructs the expected C1 request package from the supplied C task projection, exact B report, and authorization; a modified request or context is rejected;
- requires a schema-valid C2 snapshot-verification report with `status=verified`, matching case/source/task identity, matching graph fingerprint and source manifest, no mismatches, and no provider-side effects;
- revalidates the C0 authorization through the C1 package builder;
- accepts only the registered Cloudflare Qwen3.8-27B profile;
- maps the exact authorized limits to investigator-limit field names and rejects any value above 11 rounds, 12 tool calls, 2,048 tokens per normal call, 6,144 finalization tokens, 30,720 total tokens, 900 seconds, or USD 0.50;
- preserves smaller authorized limits rather than replacing them with defaults;
- imports no provider factory and does not read credentials, make network calls, or start the investigator. A separate confirmation can mark the contract ready for a later executor, but dispatch remains false.

`tests/semantic_audit/test_ae32d_c3_execution_contract.py` adds mocked, provider-free tests for the C1/C2 bindings and budget contract. `tests/semantic_audit/test_ae32d_c_request.py` now checks that the C1 package supplies the nonempty context required by the actual investigator. The Stage1 AE-32D workflow includes the C3 test file and push path. Validation of the latest commits is pending.

## 5. Remaining C3 acceptance tests

Before any live invocation, add tests proving:

1. Invalid/missing authorization prevents provider-factory import, credential lookup, and provider construction.
2. Case, source SHA, task digest, B-report digest, graph fingerprint, prompt, tool-catalog, and cost-estimator mismatches block dispatch.
3. A valid authorization maps to no more than 11 rounds, 12 tool calls, 30,720 total tokens, 900 seconds, and USD 0.50; lower authorized values are preserved.
4. The investigator receives the exact C2-verified source/graph snapshot and the exact C1 investigation requirements.
5. Unsupported provider/model profiles fail closed before credentials are read.
6. Timeout, cancellation, budget exhaustion, provider failure, invalid response, and incomplete evidence cannot produce a completed C3 report.
7. The report preserves provider/model and adapter revisions, request/response identity where available, source/graph provenance, budget consumption, error/finish status, and explicit limitations.
8. C3 does not mutate source files, apply repairs, change A/B decisions, or write benchmark gold labels.

Use mocked providers for these tests. They must not make network calls.

## 6. Next implementation sequence

1. Implement a provider-free C3 request/authorization validator and a single explicit budget-mapping function.
2. Add mocked execution tests for all authorization, snapshot, and budget boundaries.
3. Add the bounded executor behind the validated gate, keeping provider construction lazy and isolated.
4. Run the deterministic test suite and record the exact commit and workflow artifacts.
5. Only after the user separately authorizes the provider/model and budget may a live C3 execution be attempted.
6. Retain the raw C3 artifact and normalize it as a C-condition trial only after its provenance and outcome contract validate.

## 7. Current disposition

**C3 is not executed.** The provider-free C3 contract closes the request reconstruction, exact C2 snapshot binding, and budget-mapping layer, but the actual executor is still outstanding. The next code change must connect the validated contract to `RepositoryInvestigator` while preserving the mapped limits and lazy provider construction. C0–C2 remain the last validated execution boundary; the new C3 contract has not yet passed its GitHub Actions test. No benchmark score, diagnostic-accuracy improvement, or primary-benchmark eligibility is claimed.

## 8. Follow-up after C3 contract validation — 2026-11-28

### 8.1 Validation evidence

The corrected provider-free C3 execution-contract suite passed in GitHub Actions:

- Workflow run: [46063943140](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/46063943140)
- Job: `verify-candidate` ([140724642495](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/46063943140/job/140724642495))
- Validated commit: `bdecd3c2db606830e7266df2202d0fada8e64ffc`
- The complete 32-step workflow succeeded, including the C3 contract tests and the downstream machine-verification, benchmark-record, fixed-fixture boundary, and artifact-publication steps.

This validates the provider-free C3 contract and the workflow's existing deterministic checks. It does **not** validate investigator execution, provider construction, credential access, or a live C3 trial.

### 8.2 Newly confirmed executor integration boundary

Inspection of the current Stage1 implementation establishes an important lifecycle detail:

- `verify_c_graph_snapshot()` in `tools/ae32d_c_snapshot.py` reconstructs the C2 graph in a temporary directory.
- It creates `RepositoryEvidenceTools`, checks the repository summary against the B graph identity, and closes the evidence-tools instance before returning the C2 verification report.
- Therefore, the C2 report is a verification record, **not a retained graph/evidence-tools object** that C3 can pass directly to `RepositoryInvestigator`.

The C3 executor must independently reconstruct and retain the declared-scope graph for the duration of the investigation. It must repeat the exact source-revision and scope-manifest checks, compare the reconstructed graph summary against both the B report and C2 verification report, and close the evidence-tools instance only after the investigation terminates. It must not treat a successful historical C2 report as proof that a later, separately constructed graph is identical without rechecking it.

The existing helper `_scope_snapshot()` in `tools/ae32d_graph_assisted_audit.py` provides the same declared-scope projection used by B and C2. The executor should reuse that projection rather than create a subtly different copy policy.

### 8.3 Investigator construction contract

The inspected `RepositoryInvestigator` constructor accepts the already-created evidence-tools object and an explicit `InvestigationLimits` instance. The C3 adapter can therefore avoid the unsafe generic live-limit helper and construct limits directly from the validated C3 contract.

The cost estimator is available in `audit_engine/semantic_audit/ae32c/live_evaluation.py` as `build_live_cost_estimator()`. Its import and construction must remain lazy until the C3 contract and exact source/graph reconstruction have passed. The existing `build_live_investigation_limits()` must not be used unchanged: it sets `max_total_tokens=180000`, above the C3 authorization ceiling of 30720.

### 8.4 Next implementation gate

Implement a provider-free executor adapter with these ordered boundaries:

1. Rebuild the C3 contract from the exact C1/C2 inputs; fail closed on any mismatch.
2. Resolve the source checkout from the trusted case/source record and require its Git HEAD to equal the exact C1 source commit.
3. Rebuild the declared-scope graph in a retained temporary directory using the shared B/C2 scope-snapshot helper.
4. Verify the rebuilt graph's source manifest, graph fingerprint, backend, and coverage against both B and C2 before creating any provider.
5. Map the exact C3 budget into `InvestigationLimits`; preserve smaller authorized values and never inherit the 180000-token default.
6. Construct `RepositoryInvestigator` with that exact evidence-tools instance and the exact C1 source, graph, and context requirements.
7. Keep provider construction behind a lazy, explicit factory boundary. Provider-free structural tests must prove that blocked or unconfirmed requests do not import the provider factory, read credentials, construct a provider, or make network calls.
8. Test the executor with a deterministic fake provider and fault-injection cases before any live provider invocation.

No live provider invocation is authorized by the successful run. The Cloudflare Qwen3.8-27B ceiling remains 11 model rounds, 12 tool calls, 2048 normal tokens per call, 6144 finalization tokens per call, 30720 total tokens, 900 seconds, and USD 0.50. A live invocation still requires separate explicit user authorization.

## 9. C3 retained-snapshot executor boundary — implementation candidate (2026-11-28)

### 9.1 Added implementation

The Stage1 implementation now includes:

- `tools/ae32d_c3_executor.py`
- `tests/semantic_audit/test_ae32d_c3_executor.py`

The executor exposes `prepare_c3_execution(...)`, which:

1. Rebuilds the C3 contract from the exact C1/C2 inputs and requires `ready_for_c3_executor`.
2. Requires a clean checkout at the exact authorized source commit.
3. Recreates the declared-scope source snapshot using the shared B/C2 `_scope_snapshot` helper.
4. Constructs one retained `RepositoryEvidenceTools` instance over that snapshot.
5. Compares source revision, source manifest, graph fingerprint, projection version, index completeness, backend, node/edge counts and backend wiring against B and both C2 graph records.
6. Verifies that every required source/context path is indexed.
7. Maps the seven authorization-controlled limits into an explicit `InvestigationLimits` instance, applies fixed operational bounds, and reasserts the authorized values after construction.
8. Returns a context-managed `C3ExecutionSession` that retains the graph until explicitly closed.

The session's `build_investigator(provider)` and `run(provider)` methods require the caller to supply an already-created provider object. This module does not call `providers.factory.build_provider`, construct a provider, read credentials, or perform network I/O. The cost estimator is imported lazily after validation; its current `live_evaluation` module imports provider-factory definitions but does not invoke them. Provider creation remains an external operation and must not be performed until the separate live-dispatch authorization is granted. Before the investigator is constructed, the supplied object is checked for the exact Cloudflare provider identity, the single authorized Qwen model, a logical-call ceiling no greater than the authorized model-round ceiling, a normal per-call token ceiling no greater than 2,048, and a `get_stats` interface reporting zero prior logical calls, HTTP attempts, tokens and cost. This prevents a caller from passing a different adapter, a reused provider instance, or a looser local provider budget while labelling it as the authorized profile.

### 9.2 Budget mapping and enforcement

The executor does not call `build_live_investigation_limits()`; that helper still carries the incompatible 180,000-token default. It constructs `InvestigationLimits` from the exact C3 contract values and enforces the C3 profile ceilings again at the executor boundary:

- 11 model rounds; 12 tool calls
- 2,048 normal tokens/call; 6,144 finalization tokens/call
- 30,720 total tokens
- 900 seconds
- USD 0.50
- temperature 0.0

Additional investigator safeguards are set explicitly rather than inherited silently from dataclass defaults. The Cloudflare cost estimator is imported lazily only after contract, checkout, scope and graph verification. That import loads provider-factory definitions transitively through `live_evaluation.py`, but does not call the factory, construct a provider, or read credentials.

### 9.3 Tests and workflow integration

The new tests cover:

- exact authorized-limit mapping and rejection of over-ceiling values;
- comparison of every B/C2 graph-snapshot field;
- rejection of unconfirmed contracts before graph construction;
- rejection of a mismatched source checkout before graph construction;
- retained graph lifetime, required-path binding, investigator constructor arguments and cleanup;
- rejection of a mismatched provider, model, logical-call ceiling or normal token ceiling, and rejection of a provider with prior usage;
- cleanup and failure on declared-scope manifest mismatch;
- absence of eager provider-factory and credential imports in the executor module.

The AE-32D machine-verification workflow now includes this test file and runs it after the C3 contract tests. These are candidate tests until a successful Actions run is observed.

### 9.4 Current boundary

This implementation is a provider-injected execution boundary, not a live-dispatch authorization. It does not create a provider or call `RepositoryInvestigator.run()` during preparation. A caller could only start an investigation by separately supplying a provider object and explicitly invoking the session. No live provider call, credential access, or network activity is authorized by this implementation step.


## 10. Deterministic fake-provider execution coverage — implementation candidate (2026-11-28)

### 10.1 Added tests

Added `tests/semantic_audit/test_ae32d_c3_fake_provider_execution.py`. The tests use the existing deterministic AE-32C fake provider and evidence-tool fixtures; the success-path test uses a real local `RepositoryEvidenceTools` snapshot over a temporary fixture directory.

The new coverage exercises:

1. A complete fake-provider investigation through the real `RepositoryInvestigator.run()` loop, including repository summary, source-file tool dispatch, evidence-ledger construction, final diagnosis normalization, budget reporting, and snapshot re-verification.
2. Tool-call budget exhaustion after the initial repository-summary call, proving that a second evidence tool is not dispatched after the ceiling is reached.
3. Provider failure after a successful evidence retrieval, proving that prior evidence remains in the report and the investigation terminates as incomplete rather than being promoted to success.
4. Single-use investigator termination: a second invocation on the same investigator instance is rejected.

The success-path assertions bind report provenance to the local evidence-tools manifest and graph fingerprint, require `snapshot_check_status=verified`, and assert that the investigator did not execute repository code or tests. All model responses are supplied from an in-process queue. No provider factory, credentials, or network transport is involved.

### 10.2 Workflow integration

The AE-32D machine-verification workflow now includes the new test path and a dedicated step:

`Test C3 investigator lifecycle with deterministic fake provider (no network)`.

This is a candidate until GitHub Actions executes the updated workflow successfully. No local test run is claimed.

### 10.3 Exact remaining boundary

These tests validate the investigator lifecycle and its evidence/budget/failure semantics with a fake provider. They do **not yet** validate the complete `C3ExecutionSession.run()` wrapper end-to-end with the C1/C2-authorized retained graph and its post-run source-revision/provenance checks. That is the next integration test to add after this suite passes.

No live provider dispatch is authorized or performed. C3 remains a deterministic fake-provider validation stage, not an official A/B/C trial; no diagnostic-accuracy result or benchmark score is claimed.


### 10.4 GitHub Actions validation

The first run, [46067230554](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/46067230554), reached the new test step but failed because `pytest` was not installed in the workflow environment. The existing C3 contract and retained-snapshot executor steps had already passed. The failure was an explicit missing test-runner dependency, not a test assertion failure.

The workflow dependency installation was corrected to include pinned `pytest==8.4.2`. The corrected run then completed successfully:

- Workflow run: [46067341996](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/46067341996)
- Job: `verify-candidate` ([140735768976](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/46067341996/job/140735768976))
- Validated commit: `b4bcd31f1cd3262df6139050543fc09acd825435`
- Final conclusion: `success`
- The fake-provider lifecycle step passed, as did the C3 execution-contract and retained-snapshot executor steps and all downstream deterministic workflow checks.

This establishes that the new investigator lifecycle tests execute and pass in CI. It does not yet establish end-to-end success of `C3ExecutionSession.run()`; that wrapper-level integration test remains the next step. No live provider call was made.


## 11. C3 session run-wrapper guards — implementation candidate (2026-11-28)

### 11.1 Added coverage

Extended `tests/semantic_audit/test_ae32d_c3_executor.py` with direct tests of `C3ExecutionSession.run()`. These tests inject a fake investigator and a fresh fake provider profile to isolate the session wrapper's own control flow. They assert that the wrapper:

- checks the source revision before and after the investigator run;
- invokes the investigator exactly once with the contract-bound problem statement;
- rejects a report if any of source revision, source-manifest digest, or graph fingerprint differs from the authorized contract;
- rejects a report whose snapshot status is not `verified`;
- rejects a changed source revision before investigation and after investigation;
- closes retained evidence tools and the temporary directory through explicit session cleanup.

The underlying investigator's real run loop, evidence dispatch, report construction, and snapshot re-verification remain covered separately by Section 10's deterministic fake-provider tests. Taken together, these tests cover the investigator lifecycle and the C3 session wrapper's post-run acceptance checks, but they are not yet one single test that composes the actual C1/C2 graph reconstruction, session preparation, and investigator run in one invocation.

### 11.2 CI correction and validation

The first wrapper-test run, [46067504243](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/46067504243), failed because the test class referenced `C3ExecutionSession` without importing it. No production code failed. The missing test import was added.

The corrected workflow run succeeded:

- Workflow run: [46067621348](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/46067621348)
- Job: `verify-candidate` ([140736268226](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/46067621348/job/140736268226))
- Validated commit: `74337257978234bd9e75cff89d1ea03f3dac3e9e`
- Final conclusion: `success`
- All 40 successful job steps completed; no failed steps.
- C3 execution-contract tests, retained-snapshot executor tests, fake-provider investigator lifecycle tests, and C3 run-wrapper tests all passed.

No live provider call was made. This is still deterministic integration-boundary verification, not an official C3 trial or A/B/C benchmark result.


## 12. End-to-end retained C3 session composition — implementation candidate (2026-11-28)

### 12.1 Scope

Added `tests/semantic_audit/test_ae32d_c3_end_to_end.py`. Unlike the earlier executor tests, this test does not patch the C1/C2 contract builder, source revision, scope snapshot, graph backend, or evidence-tools factory. It uses the immutable pinned AE-32D negative-control case already checked out by the machine-verification workflow.

The test composes the actual sequence:

1. Build the B graph report from the pinned case and sanitized B projection.
2. Build the C0 preflight, authorization fixture, and C1 request package.
3. Run the real C2 graph snapshot verifier and require exact expected/observed graph equality.
4. Call `prepare_c3_execution()` with the same pinned source checkout, causing a second declared-scope reconstruction that is retained for the session.
5. Supply a deterministic in-process fake with the exact Cloudflare/Qwen profile identity and fresh zero-usage statistics.
6. Call `C3ExecutionSession.run()`, exercising the actual investigator lifecycle and the session's pre/post source-revision and report-provenance checks.
7. Assert completed diagnosis, verified snapshot, exact source/manifest/graph provenance, authorized budgets, graph/context discovery, and read-only execution assessment.
8. Exit the session context and assert cleanup.

The test's `manual_dispatch_confirmed=True` is a test-only readiness input for an injected fake. It does not represent user authorization for a live model call. No production provider factory, credentials, or network transport is used.

### 12.2 Workflow integration

The AE-32D machine-verification workflow now includes the new test path in its push filter and a dedicated pytest step with `AE32D_CASE_SOURCE_ROOT` pointing to the immutable case checkout. This test is an implementation candidate until the corresponding GitHub Actions run succeeds.

### 12.3 Acceptance boundary

A successful run will establish that real B/C1/C2 artifacts can be composed with a freshly reconstructed, retained C3 graph and that the actual investigator can complete against it using a deterministic fake provider. It will not establish live-provider behavior, credential safety for a production provider, diagnostic accuracy, an official C3 trial, or A/B/C benchmark eligibility.

No live provider invocation is authorized or performed by this change.


### 12.4 CI findings and estimator-import correction

The first end-to-end attempt exposed a comparison-shape issue: C2's expected snapshot includes the status marker `complete`, while the observed runtime snapshot contains the nine graph-identity fields and omits that marker. The assertion was corrected to compare the shared graph-identity fields; the verifier's own status and mismatch checks remain authoritative.

The next attempt reached C3 preparation and failed while importing `build_live_cost_estimator` from `live_evaluation.py`. That module imports `providers.factory` at module scope, which transitively imported the Cloudflare adapter and failed in the deterministic workflow environment because `requests` is not installed. No provider was constructed and no network call was attempted, but the import coupling violated the intended provider-independent preparation boundary.

Corrective refactor:

- Added `audit_engine/semantic_audit/ae32c/cost_estimation.py` as a provider-independent module containing the shared Cloudflare Qwen estimator and pricing metadata.
- Changed `tools/ae32d_c3_executor.py` to import the estimator from that module, not from `live_evaluation.py`.
- Kept the existing live-evaluation module API available; this change does not alter its live-dispatch behavior.
- Strengthened the executor AST test to reject imports of `live_evaluation` as well as provider factories and credential modules.
- Added `tests/semantic_audit/test_ae32c_cost_estimation.py` for profile selection, invalid-usage rejection, conservative pricing metadata, and the absence of provider/live-evaluation imports.
- Added the new module and test to the AE-32D workflow path filter and deterministic test steps.

The end-to-end test has not yet passed. The next Actions run must validate both the pure estimator suite and the complete C1/C2/C3 fake-provider composition before this milestone can be marked complete.


### 12.5 Retained graph-manifest assertion correction

After the provider-independent estimator refactor, the end-to-end test progressed through C3 session preparation and exposed an incorrect test assertion. The B baseline's `source_manifest_digest` is the declared-scope snapshot digest checked by `_scope_snapshot()`; the retained `RepositoryEvidenceTools.manifest_sha256` is the graph evidence manifest recorded in B's `graph_snapshot.source_manifest_sha256`. They are distinct digest fields with distinct contracts. The executor checks both at their respective boundaries. The test now binds the retained evidence-tools manifest to the B graph snapshot field and continues to assert the baseline declared-scope digest through the executor's successful preparation. The next Actions run must confirm this correction and the remaining investigator assertions.


### 12.6 Fake-provider ceiling correction

The next CI attempt passed the estimator boundary and retained-manifest assertions, then correctly rejected the fake provider because its local logical-call ceiling was 11 while the actual C1 authorization fixture grants 8 model rounds. The executor's check is intentional: a provider adapter must not advertise a looser call ceiling than the authorized contract. The integration fixture now sets the fake provider's local ceiling from the exact authorized `max_model_rounds` value rather than the profile's absolute hard ceiling. Production validation was not weakened.


### 12.7 Full C3 token-reservation envelope in the deterministic fixture

With the fake provider cap aligned, the integration reached the real investigator and correctly stopped before any provider call with `estimated_token_budget_exhausted`. The C1 helper's generic test authorization used 24,576 total tokens and 4,096 finalization tokens, which did not leave enough reservation headroom for the complete C1 problem context plus the mandatory three-round finalization reserve. This was not a provider failure; `provider_calls=0`.

The end-to-end fixture now derives its authorization from the real C0 preflight and raises only the test envelope to the already-defined C3 profile maxima: 11 rounds, 12 tool calls, 2,048 normal tokens/call, 6,144 finalization tokens/call, 30,720 total tokens, 900 seconds, and USD 0.50. The injected provider remains an in-process fake. No live dispatch is permitted by this test. The next Actions run must confirm that the authorized token reservation is sufficient and that the fake investigation completes.
