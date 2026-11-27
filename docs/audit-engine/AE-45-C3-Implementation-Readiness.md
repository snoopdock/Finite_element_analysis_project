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
