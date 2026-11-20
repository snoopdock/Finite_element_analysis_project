# ADR-080: Evidence-bound graph-utilization telemetry

- Status: Accepted
- Date: 2026-11-19
- Scope: AE-32C E.8.7, Stage1 only

## Context

E.8.1–E.8.6 established a deterministic audit and graph-assisted investigation path, graph backend selection, evidence-preserving traversal and change-set impact analysis. Existing investigation reports recorded tool calls and graph interaction coverage, but live evaluation artifacts did not expose one general, normalized utilization record across ordinary graph-assisted runs. In particular, graph follow-through, graph-evidence claim linkage, active backend identity and provider resource use were not summarized together.

The project needs to establish whether the LLM actually uses the graph engine before granting the system additional action authority.

## Decision

1. Add a pure deterministic `build_graph_utilization_assessment` function over the investigator's evidence ledger.
2. Attach the assessment to every finalized investigation report.
3. Measure tool invocation, query completion/truncation, graph-surfaced paths, verified source follow-through, claim references to successful graph-derived tool ledger entries, selected backend/runtime counters and provider resource usage.
4. Add a trusted `--graph-backend` option to the manually opted-in live evaluation runner. An explicitly selected unavailable backend fails closed.
5. Include compact graph-utilization metrics in comparison records and Markdown reports.
6. Add an offline aggregator for published comparison records, grouping only identical provider/model/backend/source-manifest combinations.
7. Keep all metrics descriptive. Do not score diagnosis accuracy, infer graph benefit, or treat ledger citation as semantic proof.

## Rationale

The evidence ledger is the authoritative record of tool invocation order, response status and source hashes. Computing utilization from that ledger avoids relying on model-authored claims about what it used. Hash-bound source follow-through is stricter than counting a read request. Claim linkage uses the investigator's existing ledger-bound evidence IDs. Backend identity and counters come from the existing runtime architecture report.

## Consequences

- Live runs produce a consistent utilization assessment without additional provider calls.
- Backend-specific live comparisons can be requested explicitly and audited.
- Multiple run artifacts can be summarized without re-running the model.
- Optional native backend availability remains a deployment constraint; the CLI does not silently substitute another backend.
- Descriptive utilization does not establish diagnostic correctness or causal improvement.
- Existing tool schemas and deterministic execution boundaries remain unchanged.
