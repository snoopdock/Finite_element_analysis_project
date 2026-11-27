# AE-45 — C3 implementation readiness and execution boundary

**Branch:** `stage1/section-uuids`  
**Baseline:** `600e1239791e6c2944a8c9edad64f08c3e04d683`  
**Status:** C0–C2 validated; C3 implementation integration audit in progress; no provider call authorized or executed.

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

The C1 request contains a bounded `investigation_requirements` object, but C3 still needs an explicit, tested mapping from those fields to the AE-32C investigator constructor. In particular, validate that:

- every required source path belongs to the exact reconstructed source snapshot;
- the required graph target is a valid target in the reconstructed graph, not merely a nonempty string;
- relation types and direction are supported by the selected graph backend;
- required context-trace fields are either complete and bound or explicitly absent;
- the investigator's graph fingerprint and source manifest match the C2-verified values.

C3 must reject unknown, omitted, duplicated, or mismatched requirements rather than silently weaken the investigation contract.

### 3.3 Source snapshot selection

C3 must derive its source/fixture root from the trusted case record and exact pinned source identity. It must not accept an arbitrary caller-supplied repository path or silently use the current branch checkout when the request names another source commit.

### 3.4 Dispatch and failure containment

The provider factory and credential-bearing environment may be accessed only after all offline checks pass and explicit manual dispatch confirmation is present. Timeouts, cost exhaustion, provider errors, malformed responses, incomplete evidence, and stale snapshot identity must remain explicit non-success outcomes. A late response must not be committed after cancellation or snapshot invalidation.

## 4. Required C3 acceptance tests

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

## 5. Next implementation sequence

1. Implement a provider-free C3 request/authorization validator and a single explicit budget-mapping function.
2. Add mocked execution tests for all authorization, snapshot, and budget boundaries.
3. Add the bounded executor behind the validated gate, keeping provider construction lazy and isolated.
4. Run the deterministic test suite and record the exact commit and workflow artifacts.
5. Only after the user separately authorizes the provider/model and budget may a live C3 execution be attempted.
6. Retain the raw C3 artifact and normalize it as a C-condition trial only after its provenance and outcome contract validate.

## 6. Current disposition

**C3 is not executed.** The next code change must close the token-budget and request-to-investigator binding gaps before any provider call. C0–C2 remain the last validated AE-45 boundary. No benchmark score, diagnostic-accuracy improvement, or primary-benchmark eligibility is claimed.
