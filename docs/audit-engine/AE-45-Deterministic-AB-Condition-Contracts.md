# AE-45 — Deterministic A/B condition contracts

**Status:** contract specification; implementation not yet enabled  
**Branch:** `stage1/section-uuids`  
**Depends on:** AE-44 controlled trial design and AE-44 G0 source mapping  
**Scope:** AE-32D exploratory A/B conditions only; C remains separately gated

## 1. Decision and boundary

AE-32D protocol v0.1 describes A as “existing deterministic audit and standard source search” and B as “A plus graph retrieval”. The current implementation does not provide an end-to-end case-level executor for either condition. AE-45 therefore specifies the missing contracts without pretending that AE-32A/AE-32B operational status is a diagnostic answer.

A and B are read-only, provider-free conditions. Neither may read the machine-reference registry, machine-verification ledger outcomes, case `ground_truth`, expected findings, provisional outcomes, adjudication fields, or any scorer output. They may read only the pinned source snapshot, task statement, declared scope, declared constraints, and explicitly permitted repository evidence.

The benchmark's primary outcome remains independently adjudicated audit quality. Until adjudication, these runs are exploratory and cannot promote case eligibility.

## 2. Shared case-input contract

The runner receives a sanitized task projection, not the full case JSON:

- `case_id`;
- `source.repository` and exact `source_commit_sha`;
- fixture/checkout locator;
- `task.title`, `task.problem_statement`, `task.declared_scope`, `task.constraints`;
- approved environment/test commands only through a separate, versioned command allowlist (not part of the task projection);
- experiment ID, condition, immutable run-envelope identity.

The projection is constructed by an allowlist. It must not serialize the `ground_truth`, `review`, machine-reference registry, AE-41 ledger, or evaluation eligibility fields into the executor process. Tests must prove the forbidden fields are absent, not merely promise that the executor ignores them.

The source checkout must resolve to the exact case SHA. Every included file is identified by repository-relative path and content SHA-256. The runner fails closed if the revision is unavailable, the checkout is dirty, a declared scope path is absent, or a source identity cannot be verified. No condition may substitute the current branch HEAD for a case-pinned SHA.

## 3. Common report contract

Both conditions emit a structured report with:

- schema/version and condition adapter revision;
- case ID, source SHA, task-contract digest, configuration digest;
- source-manifest digest and declared-scope coverage;
- explicit `decision`: `defect`, `no_defect`, or `abstain`;
- finding records with stable finding ID, statement, classification (observation/inference), exact source path and line/range, evidence digest, and evidence role;
- counterevidence and unresolved questions;
- limitation/coverage records, including truncation and inaccessible evidence;
- execution status, diagnostics, elapsed time and deterministic tool trace.

An explicit decision is mandatory for a completed report. A report without a decision is an execution/normalization error, not an implicit `no_defect`. If the permitted evidence cannot support a decision, the adapter must emit `abstain`. The report must not include confidence as a substitute for evidence.

Evidence references must resolve against the pinned manifest and file hashes. Line numbers are one-based and refer to the exact pinned bytes decoded under a declared encoding policy. Unsupported encoding, parse failure, or truncated retrieval must be represented as a limitation.

## 4. Condition A — deterministic baseline contract

### 4.1 Intended treatment

A performs the deterministic audit and standard source-search procedure, without graph retrieval and without an LLM. It is the baseline against which the incremental effect of graph retrieval is assessed.

AE-32A may be used as a deterministic architecture/wiring inventory component where that inventory is relevant, but its report is not itself a case-level decision. Its documented behavior is report-only, static and non-executing. It does not prove runtime behavior. The A adapter must therefore add a separately specified case-audit procedure rather than map AE-32A finding counts or exit status into a diagnosis.

### 4.2 Deterministic procedure

For every case, the A procedure must:

1. Validate the sanitized task projection and exact source snapshot.
2. Inventory all files in declared scope; record missing, excluded, unreadable and out-of-scope references.
3. Read declared-scope files in a canonical path order.
4. Run only explicitly allowlisted deterministic structural checks appropriate to the declared task contract (e.g. AST/control-flow inspection for Python, JSON contract validation, or a pinned fixture test). Each check is versioned and has a declared input/output schema.
5. Perform ordinary source search using a fixed, recorded query set derived mechanically from the task title, declared symbols/paths and exact contract terms. Query tokenization, normalization, ordering, result cap and stop rule are versioned.
6. Inspect bounded source ranges around returned matches; record all truncation and omitted results.
7. Assemble observations, inferences, counterevidence and limitations in stable order.
8. Apply a versioned deterministic decision rule. It may return `defect` or `no_defect` only when a registered check establishes the relevant contract violation/satisfaction under the declared scope. Otherwise it returns `abstain`.

A may not consult graph neighbors, graph paths, graph impact, graph dependencies, graph-derived related-test results, or any semantic-graph API. It may not invoke AE-32C, provider adapters, network services or external model endpoints.

### 4.3 Decision-rule discipline

A deterministic decision rule is not allowed to inspect the case's machine reference or hidden expected finding. It must derive its result from permitted source and test evidence. Rule registration includes: rule ID/version, supported case/task family, required evidence, sufficient conditions, disqualifying counterevidence, abstention conditions, and positive/negative fixtures.

A rule that only detects a lexical token or structural witness may report that witness as an observation; it cannot claim a causal defect unless the rule's tested semantics support that inference. Runtime claims require an approved pinned test/reproduction command and captured output. A rule without validated semantics can contribute evidence but cannot determine the diagnosis.

### 4.4 A output and failure states

A completed A report contains the common report fields and a deterministic trace of rules and source-search queries. It returns `abstain` where no validated rule supports a decision. Missing source, dirty checkout, incomplete required inventory, unexpected test execution, or report-integrity failure terminates as failed/error; do not turn infrastructure failure into abstention.

## 5. Condition B — deterministic graph retrieval contract

### 5.1 Intended treatment

B is exactly A's baseline plus deterministic graph retrieval. The A configuration, rules, ordinary source-search plan, evidence policy, output schema and decision policy are byte-for-byte identical. Only the declared graph-retrieval treatment is added.

AE-32B is the evidence substrate. It builds a source-evidence projection from the inspected repository and exposes a validated, bounded, read-only dispatcher. It does not execute target code and does not provide an LLM loop. Graph edges are static source observations; they are not proof of runtime execution.

### 5.2 Permitted graph operations

The fixed B policy may call only the existing AE-32B tools:

- `repository_summary` — record graph/index provenance and completeness;
- `graph_neighbors` — inspect bounded incoming/outgoing/dependency/dependent relationships;
- `graph_path` — test a bounded path between resolved entities;
- `find_related_tests` — retrieve test files related by observed import or explicit textual reference;
- `trace_execution_context` — inspect static callers, dependencies, entrypoint and workflow context.

Other tools (`search_repository`, `read_source_file`, `search_symbols`) remain part of the common baseline evidence access, not a B-only treatment. B may use their same outputs and limits as A. B must not use decision-history or case-context discovery to gain hidden benchmark metadata; those tools are outside the trial policy unless separately justified and added to the frozen protocol.

### 5.3 Fixed retrieval plan

The B adapter must not let an LLM choose queries. It uses a versioned deterministic plan:

1. Resolve each declared source path and any explicitly named symbol from the sanitized task projection.
2. Call `repository_summary` once and retain schema version, source revision, manifest digest, graph fingerprint, node/edge counts, relation counts and evidence-index status.
3. For each resolvable in-scope file/module/symbol, issue a canonical bounded `graph_neighbors` request using a frozen relation-type allowlist, direction, depth and result cap.
4. Where the task explicitly asks about a source-to-sink, caller-to-callee, or dependency relationship and both endpoints resolve, issue a bounded `graph_path` request with a frozen relation allowlist and depth cap.
5. For each in-scope production file where test relevance is material to the task, call `find_related_tests`; record whether each result is an observed import or textual reference.
6. Call `trace_execution_context` only when the task asks about execution/entrypoint/workflow reachability; its static nature must remain explicit.
7. Deduplicate results by stable evidence identity, sort canonically, and preserve every truncation/partial-coverage signal.
8. Read source for graph-returned evidence using the same pinned source reader and line/hash checks used by A.
9. Re-run the same A decision rule over the union of A evidence and graph evidence. B may only change the decision if newly retrieved, verified evidence satisfies an already registered decision rule. It may not introduce a looser B-specific threshold.

Exact relation types, directions, depths, caps, endpoint-resolution rules and per-case query plan are stored in a versioned B policy file and included in the configuration digest. No dynamic/unbounded graph traversal is permitted.

### 5.4 Graph completeness and fail-closed behavior

B must report the AE-32B evidence-index status and graph fingerprint. If graph construction is incomplete, any query is truncated, or required endpoints cannot be resolved, B marks coverage partial. It may still report bounded evidence, but it cannot claim complete graph coverage.

A graph query error does not silently fall back to A while retaining the B label. The trial is either failed or explicitly marked partial under the frozen policy. If partial B reports are permitted, the report and scorer must retain that state as a separate stratification variable. A and B must both be retained; B must never overwrite A.

## 6. Pairing and comparability invariants

For each `(case_id, source_commit_sha, task_contract_digest)` pair:

- A and B use the same sanitized task projection and source manifest.
- A's config digest is identical in both trial envelopes as the `baseline_config_digest`.
- B's config adds only the B policy digest and graph snapshot identity.
- The common source-search output, deterministic rule versions, evidence reader, timeout and report schema are identical.
- B's report contains the complete A evidence set plus graph-derived evidence; it cannot drop inconvenient baseline evidence.
- The A and B executor environments are pinned to the same runtime/dependency lock, except for explicitly declared graph dependencies.
- A/B execution order is randomized or counterbalanced when practical; order and repetition policy are pre-registered.
- Every missing, failed, partial, abstaining or timed-out condition remains in the denominator and is visible in the paired analysis.

A pair is non-comparable if any of these invariants fails. Do not repair comparability by rewriting the historical record; create a new experiment/configuration identity.

## 7. Required tests before implementation is accepted

### Input isolation
- Sanitized task projection contains no `ground_truth`, `review`, machine-reference or ledger outcome.
- Attempted access to forbidden case fields fails.
- Wrong source SHA, dirty checkout, missing declared-scope file and path traversal are rejected.

### A determinism and decision validity
- Same snapshot/task/config produces byte-identical canonical report apart from explicitly non-deterministic telemetry fields.
- Query order, file order and finding order are canonical.
- Lexical witness alone cannot force a defect decision.
- Missing decision is rejected; explicit abstention is retained.
- Positive, negative, no-defect and ambiguous fixtures exercise each registered rule and its abstention branch.
- Runtime claims require pinned test evidence; a static report cannot claim execution.

### B graph-treatment validity
- B invokes only allowlisted AE-32B operations with frozen arguments.
- No graph API is invoked by A.
- Graph snapshot fingerprint and index completeness are mandatory in B.
- Truncated graph responses remain partial and cannot be represented as complete.
- Graph evidence resolves to the same pinned file hashes as A.
- B preserves all A evidence and adds only graph-derived evidence.
- A graph query error cannot silently relabel A output as B.
- Relation-type, depth, result and traversal budgets are enforced.

### Paired parity and negative controls
- A/B baseline configuration digests match.
- B cannot see any hidden reference or expected finding.
- No provider/network call occurs in A or B.
- Source tree remains unchanged.
- Repeated runs produce identical diagnostic payloads for deterministic conditions.
- Full A evidence appears in B and is not silently filtered.
- A/B outcomes and coverage are reported separately for all six candidate cases.

## 8. Current implementation gates

| Gate | Work | Exit evidence |
|---|---|---|
| A0 | Freeze sanitized task projection and common report schema | Schemas + forbidden-field tests |
| A1 | Register first deterministic case-audit rules | Rule specs, positive/negative/abstain fixtures |
| A2 | Implement A runner | Pinned-source manual run; deterministic raw report |
| B0 | Freeze graph query policy and graph snapshot contract | Policy schema, fixed query plans and bounds |
| B1 | Implement B runner using AE-32B dispatcher | A/B paired manual run; evidence superset and provenance tests |
| AB2 | Differential/replay and negative-control suite | CI validation and retained artifacts |

No provider dispatch is part of these gates. C is a later separately authorized extension.

## 9. Current disposition and next action

AE-45 is a specification, not an implementation claim. The next coding task is A0: add strict schemas for the sanitized task projection and common condition report, plus tests proving forbidden-field isolation and exact source binding. Then implement rule registration and a small deterministic baseline on the pinned synthetic fixtures. B must not begin until A's configuration and report semantics are frozen.

The six current candidate cases remain pending independent adjudication and excluded from primary scoring. The machine-reference registry remains prohibited as an executor input. No trial has been run and no outcome has been generated by AE-45.


## 10. A0 implementation status

The strict schemas are now present at `evaluation/ae32d/sanitized-task-projection.schema.json` and `evaluation/ae32d/condition-report.schema.json`. `tools/ae32d_trial_contracts.py` builds the task projection using explicit field selection and a canonical SHA-256 digest. It validates exact lowercase 40-character source identity, nonempty task fields, unique declared scope, and safe repository-relative paths; absolute paths, parent traversal and backslash path forms are rejected.

The task projection intentionally does **not** accept executable verification commands. Command authorization needs its own reviewed allowlist and execution policy; accepting arbitrary `argv` in this first boundary would create an unnecessary command-injection surface.

`tests/semantic_audit/test_ae32d_ab_contract_schemas.py` checks schema validity, hidden-field exclusion, digest stability when hidden references change, source/condition validation, path traversal rejection, report decision requirements, infrastructure-error separation, evidence hash/line constraints and abstention.

The existing `ae32d-machine-verification.yml` workflow now runs this test module and includes the new test and helper paths in its trigger filter. **CI status has not yet been confirmed**, so A0 is implemented but not validated until the corresponding GitHub Actions run is inspected. No A/B executor or trial output exists.
