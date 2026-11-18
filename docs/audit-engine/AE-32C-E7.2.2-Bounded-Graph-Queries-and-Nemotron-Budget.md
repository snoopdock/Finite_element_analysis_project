# AE-32C E.7.2.2 — Bounded Graph Queries and Nemotron Budget

## Evidence from the prior matched pilot

The 2026-11-18 OpenRouter/Nemotron run used source commit `8988fded23d3dfa6e64a830b2342ad1153f1ba9e` and graph fingerprint `graph:cb566f8c7c58660d1ffb32f4d356ab7f`.

The graph-enabled condition attempted a required-target query at depth 4/results 50, which returned `tool_response_too_large`. Its retry at depth 2/results 20 returned 36 observations but was marked truncated. The no-provider preflight had already demonstrated that the same target at depth 2/results 30 completed with 21 discovered nodes and 36 observations, surfacing six source paths.

The graph-enabled model subsequently read five cross-module files, but the coverage evaluator correctly refused to count the truncated target query. It then spent two additional graph calls querying `RepositoryEvidenceTools` and `RepositoryInvestigator` class symbols with `CALLS`; both returned `no_match`.

The control reached 345,574 cumulative prompt characters against a 350,000 ceiling. The graph-enabled condition attempted a provider request that would have raised the cumulative total to 354,650. Both conditions therefore stopped before diagnosis. The 12,000-token finalization completion allowance was already applied; the immediate stop was the cumulative prompt-character ceiling.

## Changes

1. The graph-enabled investigator receives the graph profile's query depth and result limit. Its graph tool schemas are pinned to the successful preflight parameters: outgoing `CALLS`, depth 2, results 30. These fields are required for graph-neighbor queries in the matched treatment.
2. The model instructions explicitly prohibit repeating the required-target query after a complete result and prohibit querying class symbols as `CALLS` roots. Class endpoints should be inspected by reading the source path and line returned by the graph. Further graph traversal, if needed, should start from a returned function symbol and answer a specific relationship question.
3. The model-facing graph view is capped at eight observations and six priority source targets. The full graph response and provenance remain in the evidence ledger and final report.
4. Nemotron's cumulative prompt ceiling increases from 350,000 to 500,000 characters and its total token budget from 180,000 to 200,000. The per-call evidence cap remains 2,048 and the finalization cap remains 12,000. The time, round, tool-call, evidence-byte, and cost limits remain enforced.
5. The comparison artifact records the enforced graph query policy.
6. The G9.42 target suite now includes `test_ae32c_graph_pilot.py`.

## Interpretation and safety

The preflight query is deterministic and makes no provider calls. The model must still issue its own required-target query during the treatment. Only a complete, non-truncated query can establish graph interaction coverage. Static `CALLS` edges are not runtime traces. The full graph evidence is preserved independently of the compact model view.

The larger prompt/token ceilings are model-profile-specific to the OpenRouter Nemotron free endpoint. Cloudflare/Qwen's existing runtime profile is unchanged. Each matched pair must continue to use the same provider and model in both conditions.

## Acceptance

- G9.42 passes on the updated Stage1 commit.
- Preflight returns `complete_for_query`, `truncated=false`, and the configured source paths.
- Treatment graph tool schema enforces outgoing `CALLS`, depth 2, results 30.
- The model completes a required-target query, reads at least three distinct cross-module paths surfaced by that query, and preserves source-hash/range checks.
- Both control and treatment complete finalization within the model-specific prompt/token ceilings.
- Human review assesses the resulting diagnosis; a single pair remains exploratory.
