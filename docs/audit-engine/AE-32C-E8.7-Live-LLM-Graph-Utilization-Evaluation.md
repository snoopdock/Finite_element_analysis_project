# AE-32C E.8.7 — Live LLM Graph-Utilization Evaluation

## Purpose

E.8.7 measures whether the LLM actually uses the AE-32B graph-derived evidence tools during an investigation, follows graph discoveries with source inspection, cites graph-tool ledger evidence in its diagnosis, and what provider/backend resources are consumed.

This increment adds observability and offline aggregation. It does not add a new LLM tool, change the deterministic action boundary, or claim that graph use improves diagnostic accuracy.

## What is measured

Every finalized `RepositoryInvestigator` report now includes:

`graph_utilization_assessment` (`ae32c/graph-utilization-assessment/v1`).

The assessment contains:

1. **Graph-derived tool usage** — attempts, successes and failures for `graph_neighbors`, `graph_path`, `trace_execution_context`, `find_related_tests` and `find_workflow_context`.
2. **Graph query usage** — attempted, successful, complete, partial/truncated and failed graph queries; query direction/mode; observed relation types.
3. **Graph-to-source follow-through** — unique paths surfaced by complete graph queries; paths already read before surfacing; paths read afterwards; and paths whose complete requested source range and SHA-256 match the graph snapshot.
4. **Claim linkage** — diagnosis claims that cite successful graph-derived tool ledger evidence IDs. This is a reference-linkage measure, not semantic entailment.
5. **Backend execution** — active backend, library/version, projection type, parity mode and backend execution counters from the runtime architecture report.
6. **Provider resources** — model rounds, requests, reported tokens, prompt characters, evidence bytes, elapsed time and reported/estimated cost where available.

The assessment intentionally excludes prompts, raw provider responses, source contents, credentials and arbitrary environment values.

## Interpretation rules

- A tool call proves only that a tool was requested and recorded.
- A graph-derived source read is verified only when a registered graph-derived tool surfaced the path first, the read follows that surfacing, it returns the complete requested range, it is not truncated except for a valid end-of-file clamp, and its file hash matches the graph snapshot.
- For `find_related_tests`, only `static_import` candidates count as graph-surfaced; `text_reference` candidates are excluded from graph follow-through.
- A claim citing a graph tool ledger record is not proof that the claim is entailed by the graph observation.
- Provider-reported token/cost values and locally estimated values remain separately labelled.
- One run does not establish accuracy improvement, graph benefit, causal superiority or statistical significance.
- No human reviewers or adjudicators are required.

## Backend selection for a live run

The opt-in live evaluation runner now accepts `--graph-backend`:

- `networkx`
- `scipy`
- `igraph`
- `graph-tool`
- `snap`
- `reference` (pure-Python reference backend; comparison/control only)

The selected backend is used to construct both the baseline snapshot reader and graph-assisted evidence tools. This keeps snapshot construction consistent. Explicitly selected unavailable backends fail closed; there is no automatic fallback.

NetworkX is the default. Until the E.8.5 native conformance matrix has been completed for an optional library, use NetworkX or SciPy only. Selecting igraph, graph-tool or SNAP without a compatible installed native library should fail during initialization before provider calls.

Live calls still require the explicit `--confirm-live-provider-calls` flag. Ordinary G9.42 validation and the aggregate CLI make no provider/network calls.

Example controlled run:

```bash
python -m audit_engine.semantic_audit.ae32c.live_evaluation \
  --confirm-live-provider-calls \
  --repo-root tests/semantic_audit/fixtures/ae32c_provider_interface_incident \
  --baseline-context-path pipeline/extractor.py \
  --provider cloudflare \
  --model @cf/qwen/qwen3.8-27b \
  --graph-backend networkx \
  --require-graph-interaction \
  --required-graph-target symbol:pipeline.extractor::extract \
  --required-graph-relation-type CALLS \
  --output-dir "$RUNNER_TEMP"
```

Use the same problem, source snapshot, provider/model, required source/context contract and budget when repeating a comparison. Run a separate invocation for each backend. Repeated live runs consume provider quota; E.8.7 does not run them automatically.

## Offline aggregation

After collecting one or more published `comparison.json` files, aggregate them without further provider calls:

```bash
python tools/aggregate_ae32c_graph_utilization.py \
  --input /path/to/run-one/comparison.json \
  --input /path/to/run-two/comparison.json \
  --output-dir /path/outside/checkout
```

The tool:
- accepts 1–100 comparison files;
- rejects symlinked, oversized, malformed or duplicate evaluation inputs;
- groups results by provider, model, active backend and exact source-manifest SHA-256;
- reports descriptive totals and means;
- publishes JSON, Markdown and SHA-256 manifests atomically outside the checkout.

Runs from different source snapshots are never pooled into one group.

## Validation

G9.42 adds deterministic tests for the telemetry builder, source follow-through rules, claim linkage, backend/resource reporting, comparison artifact rendering and offline aggregation.

No provider credentials are needed for these tests. The live comparison remains manually dispatched and explicitly consented.

## Scope and non-goals

- No change to `main`.
- No changes to provider API keys or token budgets.
- No arbitrary shell, code execution, file modification or patch authority.
- No new LLM-facing function definitions.
- No human-review dependency.
- No diagnostic-accuracy score or graph-benefit claim.
