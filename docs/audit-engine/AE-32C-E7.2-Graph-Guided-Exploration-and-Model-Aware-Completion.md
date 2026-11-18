# AE-32C E.7.2 — Graph-Guided Exploration and Model-Aware Completion

## Purpose

E.7.2 is a bounded correction to the matched real-repository graph pilot. It addresses two observations from the Nemotron pilot:

1. The graph returned useful cross-module `CALLS` observations, but the model repeatedly searched for and reread the entry-point file instead of following the returned downstream paths.
2. The graph-enabled condition reached finalization with a 2,048-token completion allowance and was truncated by the provider.

This increment improves the model-facing graph view, makes cross-module source follow-through an explicit acceptance requirement, and moves provider/model runtime limits into configuration.

It does not change the graph schema, static call resolver, provider factory, or source-evidence trust boundary.

## 1. Graph response presentation

The full graph response remains in the investigator's immutable evidence ledger and final report. Only the model-facing view is compacted.

For `graph_neighbors`, the model-facing view now:

- Preserves the query status, coverage status, relation types and all surfaced source paths.
- Separates cross-module paths from the target module's own path.
- Presents `priority_source_targets` with exact repository-relative path, symbol, module, line, relation, depth, edge evidence ID and source hash.
- Selects cross-module observations before same-module observations.
- Keeps endpoint names, modules, paths, symbol lines, edge source location and static-resolution metadata.
- Caps the model-facing observation list to a small bounded set; the complete observation ledger is retained for review.

The purpose is to reduce noise without discarding the source-bound graph record.

## 2. Graph-guided exploration contract

The `ae32c_core` profile now requires three distinct, verified cross-module source reads after the required graph query.

The model is instructed to:

1. Query `graph_neighbors` for the configured target and `CALLS`.
2. Inspect `cross_module_source_paths` and `priority_source_targets`.
3. Read at least three distinct paths surfaced by that graph result, using exact paths and symbol line hints.
4. Prefer downstream modules outside the target module.
5. Avoid broad searches merely to rediscover paths already returned by the graph.
6. Avoid repeatedly reading the entry-point file.
7. Distinguish statically resolved AST observations from runtime execution.

A read counts only when it occurs after the graph query, the path was not already read, the requested line range is complete and non-truncated, and the source hash matches the graph snapshot.

The configured minimum is an evaluation requirement, not a claim that three reads are always sufficient for a correct diagnosis.

## 3. Nemotron runtime profile

Provider/model limits are read from `evaluation/ae32c/provider_model_profiles.json`.

For `openrouter` / `nvidia/nemotron-3-ultra-550b-a55b:free`:

| Limit | Value |
|---|---:|
| Evidence-gathering completion cap | 2,048 tokens/call |
| Finalization completion cap | 12,000 tokens/call |
| Maximum model rounds | 13 |
| Reserved finalization rounds | 3 |
| Tool calls | 16 |
| Total token budget | 180,000 |
| Elapsed-time budget per condition | 600 seconds |
| Invalid JSON retries | 2 |
| Finalization recovery retries | 2 |

The 12,000-token finalization cap is intentionally below OpenRouter's published free-endpoint completion maximum of 65,536 tokens and below the local adapter ceiling. The evidence-gathering allowance remains 2,048 to avoid making every investigation round unnecessarily expensive or large.

The earlier truncation occurred at the 2,048-token finalization cap. Increasing the finalization allowance gives the model room for its reasoning and the required concise structured diagnosis. It does not guarantee that a free endpoint will always complete; rate limits and availability remain provider-controlled.

The model profile records zero input/output rates for this `:free` endpoint so the pilot can run with `allow_unpriced_provider_calls=false`. Token, round, time and paired-run cost controls remain active. The configured dollar cap does not override OpenRouter's free-tier rate limits.

## 4. Cloudflare/Qwen remains supported

The Cloudflare model profile is retained explicitly:

`cloudflare` / `@cf/qwen/qwen3.8-27b`

Its profile keeps:

- 2,048-token evidence calls;
- 6,144-token finalization calls;
- 11 model rounds;
- 12 tool calls;
- 900-second per-condition elapsed limit.

The Nemotron settings do not replace or disable Qwen. The matched pilot must always use the same provider and model for both control and graph-enabled conditions. Cross-model comparisons are separate experiments and must retain provider/model identity in their artifacts.

## 5. Adding providers and models later

Add a new model under:

`providers[provider_name].models[model_id]`

Optional `runtime_limits` may override only the allow-listed `InvestigationLimits` fields enforced by `_apply_model_runtime_limits`. Unknown fields are rejected. Each new model should receive its own bounded runtime profile after checking the provider/model's context, completion, tool-call and response-format behavior.

For a new provider, register its adapter in `providers.factory.SUPPORTED_PROVIDERS`, provide its dedicated GitHub secret mapping in the main workflow, and add a provider/model profile. Do not add provider-specific logic to the graph engine or the paired-condition comparison.

## 6. Acceptance and interpretation

A successful E.7.2 treatment must:

- Complete the graph query against the exact configured target.
- Observe the required `CALLS` relationship.
- Read at least three distinct cross-module paths surfaced by that query.
- Verify requested ranges and source hashes.
- Complete finalization without token truncation.
- Preserve the same source snapshot, graph fingerprint, non-graph toolset, provider, model, problem statement and limits in both conditions.

A successful paired run demonstrates the model's graph-guided navigation under this profile. One pair does not prove general causal benefit or superiority of one provider/model. Independent review and repeated counterbalanced pairs remain necessary.

## 7. Safety boundaries

- Read-only repository inspection remains mandatory.
- Target repository code and tests are never executed by the investigator.
- Static `CALLS` relationships are not runtime execution proof.
- The complete graph response and source provenance remain available in the evidence ledger.
- Provider/model response normalization remains locally validated; no provider-enforced JSON mode is assumed for Nemotron.
