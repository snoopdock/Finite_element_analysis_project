# AE-44 — Controlled A/B/C trial-generation and capture design

**Status:** execution-boundary design; no trial has been generated  
**Branch:** `stage1/section-uuids`  
**Depends on:** AE-42 validated provisional reference registry; AE-43 readiness audit  
**Execution policy:** manual authorization only; no provider dispatch in this milestone

## 1. Decision

The next safe step is to define the trial execution contract before implementing condition runners. The current repository evidence is sufficient to define the paired-trial controls, but it is not sufficient to wire the three conditions to actual executors without guessing at the existing deterministic-audit and graph-retrieval entry points.

Accordingly, AE-44 establishes the controlled experiment protocol and explicit adapter boundary. It does **not** claim that A, B, or C can currently be executed end-to-end, and it creates no synthetic outcome records.

## 2. Experimental unit and pairing

The experimental unit is one `(case_id, source_commit_sha, task_contract_digest, experiment_config_digest)` tuple. Each unit may have at most one canonical trial for each condition in an experiment:

- `A_deterministic`: deterministic audit baseline plus ordinary source search.
- `B_graph`: exactly A's baseline plus graph retrieval. The graph backend is selected for task relevance and correctness, not treated as a performance competitor.
- `C_graph_llm`: exactly B plus bounded LLM investigation.

The same case snapshot, task statement, scope, read-only policy, evidence access, timeout policy, and outcome rubric must be used across the paired conditions. The only intended treatment difference is the declared condition delta. Any additional difference must be represented in the configuration digest and marked non-comparable.

A case is not eligible merely because it appears in the machine-reference registry. The six current references remain provisional machine-derived comparators; the case records remain pending adjudication and primary-benchmark-ineligible.

## 3. Immutable run identity

Every execution must emit a run envelope before condition work begins. The envelope must bind:

1. experiment ID and unique trial ID;
2. exact case ID and 40-character source commit SHA;
3. task-contract digest and declared scope;
4. condition name and condition-adapter revision;
5. canonical configuration digest, including rules, tools, limits and environment;
6. workflow run ID, attempt, workflow revision and run URL;
7. graph snapshot identity and retrieval configuration for B/C;
8. provider, model, prompt/template revision, tool catalog and invocation limits for C;
9. start/end timestamps as metadata, never as identity or cache keys;
10. terminal state: completed, failed, timed out, cancelled, or not executed.

The run envelope is provenance, not a diagnostic result. It must be written before the condition executes and retained even if execution fails.

## 4. Condition adapter contract

Each adapter is an isolated, read-only executor with a common interface:

- Input: immutable run envelope, pinned source checkout, task contract, and read-only evidence-tool policy.
- Output: raw condition report, execution diagnostics, and explicit terminal status.
- Prohibitions: source mutation, network access except explicitly authorized C provider calls, cross-case state, hidden access to machine-reference outcomes, and writing to benchmark ground truth.
- Reproducibility: report deterministic configuration and environment; C additionally records provider/model and prompt/tool revisions.

### A — deterministic adapter

Must invoke the actual deterministic audit implementation and ordinary source-search mechanism. It must not use the provisional machine-reference outcome as an input. The output must preserve findings, evidence references, coverage, abstentions and errors separately.

### B — graph adapter

Must invoke A's exact baseline configuration and add graph retrieval as the only treatment difference. It must record the graph snapshot, backend/adapter version, query/retrieval parameters and returned evidence provenance. Backend choice is task-specific; do not create a universal backend ranking.

### C — bounded LLM adapter

Must invoke B's exact graph-assisted configuration and add the explicitly authorized provider/model investigation. It must be read-only, bounded by declared wall-clock, token/call and monetary ceilings, and must record actual usage. No credentials are exposed to A/B. No push, pull-request, schedule, or default workflow event may dispatch C.

## 5. Outcome normalization

A raw report is not a normalized outcome. A separate deterministic normalizer must map an explicit structured decision from the condition output to exactly one of:

- `defect`
- `no_defect`
- `abstain`
- `error`

The normalizer must not infer a diagnostic outcome from process exit code, protocol completion, number of citations, evidence coverage, lexical witnesses, confidence score, or model success. If the condition report lacks an explicit decision, normalization fails and the trial remains an error/unresolved record.

The raw report is immutable. Normalized output records the normalizer version and digest of the raw report. Corrections create a new normalization record; they do not rewrite the raw report.

## 6. Manual dispatch and authorization

Execution is split into two authorization levels:

- **A/B:** explicit manual workflow dispatch, selecting a case and condition, with no secrets and no source-write permission.
- **C:** separate explicit authorization gate. The operator must affirm the provider/model, maximum spend, maximum calls/tokens, and approved prompt/tool revisions before any credential is made available to the job.

A generic `workflow_dispatch` event is not sufficient authorization for C. The workflow must reject C unless all C-specific authorization inputs are present and within repository-configured hard ceilings. No provider secrets are passed to preparation, validation, or A/B jobs.

Until actual adapter entry points and hard ceilings are identified and tested, the workflow must remain a design/preflight-only workflow. It must not claim to have executed a condition.

## 7. Failure, retries, and pairing

- A failed, timed-out, cancelled or interrupted trial is retained with diagnostics and is never silently retried as if it were the same trial.
- A retry receives a new trial ID and links to the prior attempt.
- Missing condition outputs are reported as missing, not dropped from the paired set.
- Duplicate `(experiment, case, condition, canonical attempt)` records are rejected.
- A/B/C outputs with different source, task, scope or baseline configuration are non-comparable.
- Concurrent completion order does not determine publication order; the immutable experiment manifest is assembled only after validating all referenced trial envelopes and artifact digests.

## 8. Artifact layout

The eventual immutable bundle should contain:

```text
experiment-<id>/
  experiment-manifest.json
  trials/
    <trial-id>/
      run-envelope.json
      raw-report.json
      diagnostics/
      normalized-outcome.json
      artifact-manifest.json
```

The artifact manifest records relative paths, byte sizes and SHA-256 digests. Reject absolute paths, parent traversal, symlinks and duplicate paths. Raw reports and diagnostics are retained for failed trials as well as completed ones. The importer must verify digests before parsing content.

## 9. Required acceptance tests

Before enabling any executor, test at least:

1. exact source SHA and task digest binding;
2. condition mismatch and cross-case artifact rejection;
3. duplicate trial and retry identity rejection;
4. raw artifact digest mismatch and post-capture mutation;
5. path traversal, absolute path, symlink and duplicate-path rejection;
6. explicit abstention versus missing decision versus execution error;
7. failure and timeout retention;
8. C authorization absent, malformed, over-budget and under-specified cases;
9. A/B jobs receive no provider secrets;
10. C cannot run on push, pull request, schedule or workflow-call triggers;
11. B/C graph snapshot identity and retrieval configuration required;
12. no mutation of case records, ground truth, machine-reference registry or primary eligibility;
13. same paired configuration except for the declared treatment delta;
14. deterministic normalization replay from the same raw report.

## 10. Implementation gates

| Gate | Work | Exit evidence |
|---|---|---|
| G0 | Identify and document actual A/B/Baseline/graph executor entry points | Source-level call graph and tests; no inferred command names |
| G1 | Define run-envelope and raw-artifact schemas | Strict schemas plus negative tests |
| G2 | Implement offline artifact verifier/normalizer | Real sample bundle, digest and path-safety tests |
| G3 | Implement A adapter | Manually dispatched, pinned-source run and retained raw artifact |
| G4 | Implement B adapter | Paired A/B run with graph snapshot and retrieval provenance |
| G5 | Implement C authorization and adapter | Explicit approval, budget enforcement, secret isolation and retained provider usage |
| G6 | Assemble paired experiment and feed AE-42 scorer | Complete/missing/error visibility; exploratory-only report |

Do not skip G0. The repository's graph-native backend adapters and the AE-32D graph-retrieval condition are separate concepts: the existence of backend adapters does not prove that the audit investigation pipeline actually calls them.

## 11. Current disposition

AE-44 is a design milestone only. No A/B/C condition was executed, no provider was called, no cost was incurred, and no trial outcome was generated. Next implementation work is G0: inspect the actual deterministic audit and graph-retrieval call paths, then map each to a narrow adapter contract. Only after that source-level mapping should workflow code be added.

AE-42 remains validated. AE-43 remains blocked on qualifying raw A/B/C artifacts. The six machine-derived references remain provisional and must never be promoted to gold adjudication or primary benchmark eligibility by this work.
