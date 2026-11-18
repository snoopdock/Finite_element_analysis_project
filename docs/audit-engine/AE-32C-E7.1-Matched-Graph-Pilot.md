# AE-32C E.7.1 — Matched Real-Repository Graph Pilot

**Status:** implementation package prepared for `stage1/section-uuids`; manual workflow supplied separately for `main`.

## Objective

The first E.7 pilot established that Qwen can call the graph tool and follow graph-surfaced source paths in a controlled nine-file fixture. That result demonstrated protocol integration, but it did not establish graph value on a real Audit Engine subsystem or separate graph contribution from the additional tools and reasoning time available to the graph condition.

E.7.1 addresses those two limitations with one bounded, matched pair:

- **Control:** interactive repository investigation with ordinary source/evidence tools; graph query tools are not exposed.
- **Treatment:** the same investigation with the same source snapshot, provider/model, problem, and limits; graph query tools are exposed and graph interaction is required.

The intervention is graph-tool availability plus the corresponding graph-use instruction. A single pair is exploratory and is not sufficient to establish causal benefit.

## Real-repository subsystem

The default `ae32c_core` scope profile preserves repository-relative paths and copies a bounded Python-only source slice to a temporary directory outside the checkout.

Included source groups:

- `audit_engine/semantic_audit/ae32a`
- `audit_engine/semantic_audit/ae32b`
- `audit_engine/semantic_audit/ae32c`
- `audit_engine/semantic_audit/core`
- `audit_engine/semantic_audit/graph`
- `providers`
- six selected AE-32B/AE-32C regression-test modules and package initializers

The profile enforces at most 100 files and 2,000,000 bytes. The supplied snapshot produced a 96-file, 1,449,200-byte scope.

The graph target is:

```text
symbol:audit_engine.semantic_audit.ae32c.live_evaluation::main
```

The required relationship is `CALLS`. The investigation asks the model to trace the live-evaluation orchestration through provider construction, evidence tools, the investigator, and comparison publication. It must distinguish static AST call observations from imports, workflow relationships, and runtime execution.

## Matched experiment controls

Both conditions use:

- the same bounded source-scope manifest;
- the same source-manifest hash and graph fingerprint;
- the same provider and model;
- the same problem statement;
- the same investigation limits;
- the same ordinary source/evidence tools.

The control's tool schema omits `graph_neighbors` and `graph_path`. The treatment exposes them and requires a successful query against the configured target plus a subsequent read of a newly surfaced source path.

The runner records condition order. The default is `control-first`; `graph-first` is available for a later counterbalanced pair.

## Telemetry corrections

The prior E.7 graph-follow-through calculation counted any read path that intersected graph-surfaced paths, including files read before the graph query. E.7.1 changes the calculation:

A graph-derived read is counted only when the path:

1. was surfaced by a successful, complete graph query against the required target;
2. had not already been read before that query; and
3. was read after that query with a complete requested source range; and
4. the read source hash matches the hash carried by the graph snapshot for that path.

The evidence tool's existing `source_range_complete` field means that the entire file was returned; it is not required for a useful bounded read. E.7.1 separately computes `requested_range_complete` from the requested and returned line bounds, truncation state, and EOF clamping.

The report now records:

- every successful complete graph query, its target, evidence ID, ledger position, and observed relationship types;
- read evidence IDs and ledger positions;
- source path, full-file `source_range_complete`, calculated `requested_range_complete`, and source hash comparison for each graph-to-read follow-through;
- separate surfaced/read paths and hash-verified complete requested-range graph-derived reads;
- compact observations from all successful complete graph queries, containing endpoint IDs and descriptions, relationship type, depth, source path/line/hash, observation method, and static-resolution status;
- observation count and truncation status.

The compact observation records are review evidence, not a claim that the graph is complete or that an edge executed at runtime.

## Provider and model extensibility

The pilot uses `providers.factory.SUPPORTED_PROVIDERS` and `build_provider`; it does not contain a Qwen-only provider branch. The model ID is a free-form bounded string passed to the selected provider adapter.

Provider/model pricing is a separate optional registry in:

```text
evaluation/ae32c/provider_model_profiles.json
```

A pricing entry supplies input/output rates, an output-reservation multiplier, and an uncertainty margin. The supplied profile carries forward the current Cloudflare Qwen estimator. If a provider/model has no pricing entry, the live runner requires the explicit `--allow-unpriced-provider-calls` flag; hard token, call, and elapsed-time limits still apply, but no dollar cap is claimed.

Adding a provider requires registering its adapter in `providers.factory` and mapping its secret into the manual workflow. Adding a model to an existing provider normally requires only passing its model ID and, optionally, adding a pricing entry.

## Local preflight result on the supplied Stage1 snapshot

The bounded scope preflight completed without provider calls:

| Measure | Result |
|---|---:|
| Scope files | 96 |
| Scope bytes | 1,449,200 |
| Graph nodes | 1,217 |
| Graph edges | 5,514 |
| `CALLS` edges in graph projection | 2,992 |
| Candidate call sites | 12,603 |
| Resolved call edges in call-graph summary | 3,018 |
| Unresolved call sites | 9,585 |
| Required target query observations | 21 |
| Surfaced source paths | 5 |

The investigator's snapshot re-verification also returned `(True, "ok")` for this scope.

The graph projection's 2,992 `CALLS` edges differ from the call-graph summary's 3,018 resolved call edges by 26. This package does not reconcile that difference; it should be inspected before making graph-completeness claims.

These are local preflight measurements on the supplied Stage1 snapshot. They are not GitHub G9.42 results and do not represent a live provider evaluation.

## Acceptance boundary

The paired pilot is technically complete when:

- [x] graph tools can be disabled for a matched control;
- [x] graph tools remain available for the treatment;
- [x] graph follow-through excludes paths read before graph discovery;
- [x] compact graph observations preserve edge/source provenance;
- [x] the bounded real-repository scope preflights successfully;
- [x] provider/model selection is not hard-coded to Qwen;
- [ ] the Stage1 corrective patch passes a fresh manual G9.42 run;
- [ ] the main manual workflow is installed and pushed;
- [ ] the live matched pair completes;
- [ ] a human reviewer assesses relationship correctness and investigation quality.

A successful live pair demonstrates that the protocol ran and provides comparative evidence. It does not automatically establish diagnostic accuracy or causal graph benefit.

## Scope exclusions

This increment does not add:

- complete Python call-graph resolution;
- runtime tracing or test execution;
- embeddings or vector retrieval;
- a graph database migration;
- a generalized causal-claim entailment engine;
- multi-provider batch orchestration;
- automatic code changes or repository mutation.
