# AE-32C E.7.2.3 — OpenRouter Retry and Citation Hardening

## Why this increment exists

The preceding G9.42 validation passed on Stage1 commit `80c229cf5adc33ab403eb73e58424bc1541a7bee`:

- Python 3.11.18.
- Full regression: 3,422 passed, 8 skipped.
- G9.42 targeted selection: 432 passed.
- Independent validation-engine tests: 53 passed.

The subsequent matched pilot `44356208736` did not complete:

- Control: `finalization_recovery_budget_exhausted` after 13 model rounds.
- Control prompt characters: 434,650 of 500,000.
- Control reported tokens: 151,272 of 200,000.
- Control finalization rejection codes included `claim_evidence_reference_unresolved`, `root_cause_evidence_reference_unresolved`, and `source_reference_hash_not_in_manifest`.
- Graph-enabled treatment: OpenRouter HTTP 429 before its first model response; zero model-issued graph queries.

The graph preflight itself passed without provider calls. It indexed 96 files and produced a complete static graph snapshot. The treatment failure is therefore not evidence of a graph-engine defect.

## Corrections

### 1. Stable source-reference candidate IDs

Finalization prompts now expose stable candidate IDs such as `SRC0123456789abcdef` with the observed evidence ID, path, and line. The candidate ID is derived from the exact ledger tuple `(evidence_id, path, line, source_sha256)`.

The model cites the candidate ID; AE-32C resolves it against the current successful evidence ledger and source manifest. The model no longer has to reproduce a 64-character source hash.

Candidate IDs are stable as the ledger grows during one investigation. The candidate index is balanced round-robin across source paths so a single large file does not consume the entire compact list.

Legacy four-field source tuples remain accepted. If their supplied hash or evidence ID is wrong, AE-32C may repair the tuple only when the exact path/line is present in successful ledger evidence and the resulting source hash matches the current source manifest. Ambiguous or unobserved locations still fail closed.

Unknown evidence IDs are dropped only when a valid ledger-bound source reference supplies a real evidence ID for that same root-cause or claim. A root cause or claim with no remaining successful evidence reference is still rejected. The evidence gate is not bypassed.

The labelled-text response normalizer accepts the new candidate-ID form and retains compatibility with legacy full tuples.

### 2. Bounded OpenRouter transport retry

The investigator previously forced OpenRouter transport calls to one HTTP attempt. E.7.2.3 adds a model-profile-controlled `max_provider_transport_retries` allowance.

Nemotron receives one additional transport attempt per condition. This is not an unbounded retry loop and does not change the model-round or tool-call budgets.

For HTTP 429:
- Honor numeric `Retry-After` values.
- Honor HTTP-date `Retry-After` values.
- Clamp provider-requested waits to 60 seconds.
- If no usable header exists, wait 15 seconds before the first retry (30 seconds on a subsequent retry if configured).

Retry counts, wait totals, last wait, and retry status counts are included in safe provider telemetry.

### 3. Spacing between matched conditions

The Nemotron profile now waits 60 seconds between control and graph-enabled conditions. This reduces immediate back-to-back calls to a free/rate-limited endpoint. It cannot override a provider quota or guarantee that a 429 will clear.

The pair still uses the same provider, model, source snapshot, problem, non-graph tools, and investigation limits. There is no automatic mid-pair failover to Qwen or another model.

### 4. Better control-condition navigation instructions

The graph-disabled control is instructed to call `trace_execution_context` with the repository-relative file path:

`audit_engine/semantic_audit/ae32c/live_evaluation.py`

The tool description now clarifies that this tool resolves file/module targets, not function-level symbol IDs.

Both conditions are instructed not to reread completed ranges. If a read is truncated, only the missing, non-overlapping range should be requested.

## Budgets

No token or prompt budget increase is made.

The preceding control used 434,650 prompt characters and 151,272 reported tokens, below the existing 500,000-character and 200,000-token limits. Its failure was reference rejection/recovery exhaustion, not budget exhaustion.

Nemotron retains:
- Cumulative prompt ceiling: 500,000 characters.
- Total token budget: 200,000.
- Finalization completion cap: 12,000 tokens/call.
- Evidence completion cap: 2,048 tokens/call.
- 13 model rounds.
- 16 tool calls.
- 600 seconds per condition.

Cloudflare/Qwen's model profile is unchanged.

## Provider/model extensibility

`max_provider_transport_retries` and `inter_condition_cooldown_seconds` are generic provider/model profile settings. Future model profiles can choose their own bounded values.

The graph engine, evidence ledger, citation resolver, and paired-condition logic remain provider-neutral. A new provider still requires adapter registration and a dedicated GitHub secret mapping.

## Validation performed for this package

- All 31 G9.42 target modules: **438 passed** locally.
- Six directly affected test modules: **118 passed** locally.
- Python 3.11 grammar parsing: passed for all modified Python files.
- Python compilation under the local interpreter: passed.
- Provider/model JSON and G9.42 YAML parsing: passed.
- Full regression was not rerun to completion for this package in the local environment. A fresh GitHub G9.42 run is required.
- No live provider calls were made while preparing this package.

The local runtime was Python 3.13.5. GitHub Actions Python 3.11.18 remains the authoritative runtime acceptance gate.

## Scope

Apply only to `stage1/section-uuids`. No `main` workflow replacement is included or required. The existing main-branch manual matched-pilot workflow remains in use.
