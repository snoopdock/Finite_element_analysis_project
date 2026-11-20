# AE-32C E.8.6.1 — Live Investigation Completion and Graph Follow-Through

## Purpose

Correct the two live-evaluation failures recorded after the runtime installation correction.

This increment addresses the investigation protocol after the provider is successfully reached. It does not change the provider credentials, model selection, API endpoints, source fixture, graph projection, or main-branch workflow.

## Evidence examined

### Manual validation

Run `44688299166` validated Stage1 commit:

`f55f10d5438b297b423f7e5d456f7eff6969d8ad`

Results:

- Validation-engine tests: 53 passed.
- G9.42 targeted profile: 658 tests, 6 skipped, 0 failures, 0 errors.
- Full regression: 3,579 tests, 14 skipped, 0 failures, 0 errors.
- Detached evidence verification: passed.
- Immutable evidence publication: passed.
- Provenance catalog verification: passed.

The targeted profile has 44 test modules and does not include the two unuploaded E.8.7 graph-utilization test modules. These results validate the E.8.6 source state only.

### Cloudflare live run `44691144158`

- Provider/model: Cloudflare / `@cf/qwen/qwen3.8-27b`.
- Runtime and CLI preflights passed.
- Provider requests: 8.
- Provider responses received: 7.
- Evidence tool calls completed: 9.
- The model queried `symbol:pipeline.extractor::extract` for outgoing `CALLS`.
- The query returned `no_match`, because `extract` is called by `main.main` and `tests.check_extractor_contract`; the target function does not itself call another function.
- The final native response-tool arguments were malformed. The Cloudflare adapter returned a provider-level error (`Native response-tool arguments invalid`) instead of preserving the malformed arguments as inert data for AE-32C's existing normalizer/recovery path.

No diagnosis was accepted.

### OpenRouter live run `44691257959`

- Provider/model: OpenRouter / `nvidia/nemotron-3-ultra-550b-a12b`.
- Runtime and CLI preflights passed.
- Provider requests/responses: 10 / 10.
- Evidence tool calls: 10, of which 8 completed.
- The model completed static context tracing, read `main.py`, `providers/factory.py`, and `tests/checks.py`, searched related tests, and discovered case context.
- It never called `graph_neighbors`.
- Finalization rounds 9 and 10 were rejected because the required graph interaction was incomplete.
- Round 11 stopped with `finalization_context_budget_unavailable`: 22,767 prompt characters remained, while the smallest attempted evidence-preserving finalization context was 29,368 characters (6,601-character shortfall).

No diagnosis was accepted.

## Root causes confirmed against the fixture

The controlled target is:

`symbol:pipeline.extractor::extract`

A native query against the exact fixture produced:

| Direction | Result | Observed relation | Source paths |
|---|---|---|---|
| outgoing | `no_match` | none | `pipeline/extractor.py` |
| incoming | complete | `CALLS` | `main.py`, `pipeline/extractor.py`, `tests/checks.py` |
| both | complete | `CALLS` | same paths |

The graph direction in the live investigator prompt was hard-coded to `outgoing`. This was semantically wrong for the selected target: the target is called by other functions.

The two providers also spent scarce model turns differently. Cloudflare did perform the graph query, but in the wrong direction. OpenRouter spent its turns on context discovery and finalization without performing the mandatory graph query.

## Changes in this increment

### 1. Explicit graph direction

`RepositoryInvestigator` now accepts `required_graph_direction` (`incoming`, `outgoing`, or `both`). The controlled live evaluation defaults to `incoming` for this caller-target investigation.

The exact direction is used consistently in:
- the graph tool schema,
- the initial investigation contract,
- the operating-limit telemetry,
- the deterministic required-target query.

The live evaluation pins a bounded depth-1, 20-result query.

### 2. Deterministic prefetch, model-led follow-through

When the controlled live evaluation requires complete context and graph interaction, the auditor performs:
- one bounded `graph_neighbors` query against the required target;
- one bounded `trace_execution_context` query against the required module.

Both are recorded in the authoritative evidence ledger before the first LLM turn.

This does **not** make the LLM a passive summarizer. The live profile requires a minimum of one source-hash-verified cross-module read.

The model must still:
- inspect the returned graph observations and source paths;
- read at least one newly surfaced source file after the graph query;
- inspect the required context paths;
- complete related-test and case-context discovery;
- produce the evidence-bound diagnosis.

The telemetry distinguishes `orchestrator_prefetch` from `model_requested` graph calls. An orchestrator-prefetched query is not misreported as an LLM-requested graph call. A model-requested, source-hash-verified follow-through read is required to complete the graph-interaction contract.

### 3. Smaller finalization context

When exact required source-line anchors are configured, finalization now exposes only the source-reference candidates matching those anchors rather than every incidental line candidate from all inspected files.

The finalization prompt also receives a compact graph-coverage summary rather than the full graph observation/trace object. The complete graph telemetry remains in the final report.

This preserves:
- evidence IDs and response hashes;
- exact anchor candidate IDs;
- graph target and required relations;
- observed relations and source paths;
- verified graph-follow-through paths;
- the distinction between orchestrator prefetch and model-requested graph calls.

### 4. Cloudflare native response recovery

A completed Cloudflare HTTP response with malformed or non-object native response-tool arguments is now preserved as inert `ProviderToolCall` data, within the existing response-size limit.

The provider adapter does not execute the returned function. AE-32C's normalizer remains authoritative and rejects malformed arguments without echoing them into logs. During evidence gathering, the existing bounded response-contract downgrade can then switch to plain text and continue.

The provider now reports a separate `native_tool_call_contract_rejections` counter. These model-response contract errors are no longer misclassified as provider transport failures.

## Validation performed locally

- Real-fixture incoming/outgoing/both graph query comparison: passed.
- Real-fixture deterministic graph/context prefetch integration test: passed.
- Required `CALLS` observations: passed for incoming query.
- Model-requested graph-follow-through reads: passed; source hashes matched.
- Orchestrator vs model graph-query telemetry separation: passed.
- Finalization context compaction with required source anchors: passed.
- Cloudflare duplicate-key native arguments preserved for local rejection: passed.
- Cloudflare non-object native arguments preserved for local rejection: passed.
- Investigator native-response recovery and plain-text downgrade: passed.
- Python compilation: passed.

No provider calls were made during local validation.

## Interpretation and limitations

The two uploaded live runs do not establish diagnostic accuracy because neither produced an accepted final diagnosis.

The new prefetch query is an orchestrator action. It must not be counted as LLM graph-tool selection. The LLM's graph use is measured separately through its post-query source inspection and any additional graph tool requests.

Graph relationships remain static evidence. Incoming `CALLS` edges show statically observed callers; they do not prove runtime execution or causality.

The patch is not a claim that either provider will now complete successfully. Fresh GitHub G9.42 validation and a new live run are required.

## Installation boundary

All repository changes in this increment belong under:

`stage1/section-uuids`

Do not modify `main` or the main-branch live-evaluation workflow. The new graph direction defaults to `incoming` in the live-evaluation CLI, so the existing workflow invocation remains compatible.

Suggested commit:

`AE-32C E.8.6.1: stabilize live graph investigation and finalization`
