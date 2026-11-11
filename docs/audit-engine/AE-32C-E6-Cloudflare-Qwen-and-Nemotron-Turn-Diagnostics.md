# AE-32C E.6 — Cloudflare Qwen Preflight and Nemotron Turn Diagnostics

**Status:** Prepared for repository upload; not yet G9.42-validated or live-preflight-tested.

## 1. Scope

This increment adds two bounded capabilities:

1. A Cloudflare model-aware compatibility preflight for `@cf/qwen/qwen3.8-27b`.
2. Sanitized investigation-turn and required-source-prefetch diagnostics to explain first-turn final submissions observed with OpenRouter Nemotron Free.

It does **not** change provider defaults, the live evaluation sequence, the minimum-model-round acceptance rule, evidence requirements, source-citation requirements, or diagnostic-accuracy review.

## 2. Cloudflare Qwen model selection

The Cloudflare provider default remains unchanged:

`@cf/meta/llama-3.1-8b-instruct-fast`

The Qwen model is selected only as an explicit preflight override:

`@cf/qwen/qwen3.8-27b`

The existing `ae32c-provider-compatibility-preflight.yml` workflow already accepts a provider-specific model override. No `main` workflow change is required for this model-only preflight.

### Request mode

Cloudflare's Qwen 3.8 27B model page lists function calling and reasoning. Cloudflare's current JSON Mode supported-model list does not list `@cf/qwen/qwen3.8-27b`.

Therefore, this preflight does not assume that Qwen supports API-level `response_format`. It uses:

- ordinary chat for the transport probe;
- ordinary chat for the JSON action probe;
- strict local JSON parsing, duplicate-key rejection, non-standard-constant rejection, and exact action-schema validation.

The preflight makes two bounded provider requests. It does not invoke repository evidence tools and does not run an investigation. A passing result establishes only transport and action-envelope compatibility, not native tool-call support, multi-turn reliability, or evidence quality.

Models explicitly present in Cloudflare's published JSON Mode allowlist continue to use API-level JSON-object mode. Other models use plain chat and local validation.

## 3. Nemotron first-turn finalization diagnostics

### Observed E.5 evidence

In round-robin run `43010687485`, OpenRouter rounds 3 and 4 reported:

- `model_rounds_used = 1`;
- `tool_calls_used = 3`;
- one recorded model action: `final_accepted` at round 1;
- three evidence tool calls: `repository_summary`, `read_source_file` for `pipeline/extractor.py`, and `read_source_file` for `providers/adapter.py`.

The investigator deterministically prefetches caller-declared required source files before the first model response. The three tool calls in these reports therefore do not represent three model-requested tool actions. The model received the summary and prefetched source evidence, then submitted an accepted final action on its first model turn.

This is a supported explanation for the observed one-turn outcome in these two trials. It does not establish that every Nemotron first-turn final has the same cause.

### New diagnostics

The investigation report adds `interaction_diagnostics` with:

- number of required source paths;
- completed, incomplete, and skipped prefetch counts;
- tool-call count before the first model turn;
- model-turn count;
- first and terminal recorded model actions;
- number of model-requested tool actions;
- whether the final action was accepted on the first model turn;
- a bounded classification distinguishing first-turn finalization after complete prefetch from other first-turn or multi-turn outcomes.

The batch summary copies these fields into per-trial metrics. It does not use them to alter the gate.

### Acceptance remains unchanged

The `multiple_model_rounds` requirement remains in force. The diagnostics do not force the model to make an unnecessary tool call, manufacture an extra turn, or relabel a one-turn final as a multi-turn investigation.

Any future change to that acceptance rule requires a separate decision supported by a controlled experiment and a revised validation contract.

## 4. Security and evidence boundaries

- No raw model response text is added to diagnostics.
- No credentials, request bodies, or provider-controlled error messages are added.
- Prefetch diagnostics record counts and action categories, not source contents.
- Existing source hashes, evidence IDs, citation validation, and source-textual-support checks remain authoritative.
- A passing preflight is not evidence of diagnosis accuracy.
- Human review remains required.

## 5. Validation and operating sequence

After uploading the Stage1 files:

1. Run G9.42 against the new exact Stage1 commit using the existing main validation engine.
2. Require all declared targeted and full-regression tests to pass.
3. From `main`, run **AE-32C Provider Compatibility Preflight** with:
   - provider: `cloudflare`
   - model: `@cf/qwen/qwen3.8-27b`
   - the successful G9.42 run ID for the exact Stage1 commit
   - explicit live-call consent enabled.
4. Review `preflight.json`, `preflight.md`, and the workflow logs.
5. Do not launch a new eight-trial batch based on preflight alone.

A Qwen preflight pass permits a later controlled Qwen investigation trial to be considered. It does not authorize replacing the active Cloudflare model default or bypassing G9.42.

## 6. References

- Cloudflare Qwen 3.8 27B model page: https://developers.cloudflare.com/workers-ai/models/qwen3.8-27b/
- Cloudflare JSON Mode and supported-model list: https://developers.cloudflare.com/workers-ai/features/json-mode/
- Cloudflare Qwen 3.8 27B announcement (17 August 2026): https://developers.cloudflare.com/changelog/post/2026-08-17-qwen-3.8-27b-workers-ai/
