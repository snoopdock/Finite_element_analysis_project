# AE-32C E.7-R.3N.7.3 — Cloudflare Stream Resilience and Investigation Continuity

**Status:** Corrective implementation prepared; GitHub validation pending  
**Target Stage1 branch:** `stage1/section-uuids`  
**Expected Stage1 base commit:** `8ab027d5f4debc679874b4f73fabc65e267d378c`  
**Expected main base commit:** `b30794ffd148dc0349e8c2dbefee7ddc92c6e638`  
**Triggering live evaluation:** `43909419050`  
**Triggering G9.42 validation:** `43908925325`  
**Provider/model:** Cloudflare Workers AI / `@cf/qwen/qwen3.8-27b`

---

## 1. Triggering evidence

The N7.2 live evaluation used the exact validated Stage1 commit `8ab027d5f4debc679874b4f73fabc65e267d378c` and main workflow commit `b30794ffd148dc0349e8c2dbefee7ddc92c6e638`.

The run established that:
- G9.42 validation and independent evidence/provenance checks passed.
- The baseline completed with `finish_reason=stop`, using the 4,096-token allowance.
- The required-target trace recovered from an `argument_out_of_range` failure and ended as `completed_with_retry`.
- Required source context reads and source snapshot verification passed.
- Graph-assisted investigation ended with `provider_failure`.
- The last provider request returned HTTP 200, but the SSE consumer classified the response as `invalid_stream` / `StreamProtocolError`.
- The failed request reported 16 stream events, zero output characters, zero reasoning characters, no finish reason, and one attempt.
- No final source references were produced; final citation validation and overall discovery completeness correctly failed.

The uploaded logs do not include raw SSE frames. They establish the adapter's protocol failure classification and safe counters, but do not prove whether Cloudflare emitted malformed SSE or the adapter rejected a valid but incomplete response. N7.3 therefore hardens both protocol classification and recovery without claiming a provider-side root cause.

## 2. Bounded stream recovery

### 2.1 Recovery eligibility

The Cloudflare adapter may attempt one non-streaming recovery request only when:
- the initial request used SSE streaming;
- the stream parser reports one of the explicitly eligible protocol failures (`incomplete_stream`, `malformed_stream_event`, `invalid_stream_event_shape`, or `provider_stream_error`);
- no content delta has been received;
- no reasoning delta has been received;
- no tool-call delta has been received;
- the provider-instance fallback allowance has not already been used;
- fallback is enabled by configuration.

The hard maximum is one fallback request per provider instance. `FEA_LLM_STREAM_FALLBACK_MAX_ATTEMPTS` is clamped to 0 or 1. The default is one; `FEA_LLM_STREAM_FALLBACK=false` disables it.

### 2.2 Non-streaming fallback request

The fallback:
- reuses the same logical messages, model, tool definition, response token limit, temperature, reasoning effort, and Qwen template parameters;
- changes only `stream` to `false`;
- removes the SSE `Accept` header;
- is sent through the same OpenAI-compatible Chat Completions endpoint;
- is counted as an additional HTTP attempt within the same logical model round;
- does not trigger an automatic second fallback.

The adapter returns any native response-tool call as inert `ProviderToolCall` data. It does not execute tools. Existing response normalization, action validation, evidence-tool authorization, and investigator dispatch remain authoritative.

### 2.3 No-replay rule

No fallback or replay occurs when any content, reasoning, or tool-call delta has been received. Read timeouts remain non-replayable because provider execution may have continued after the client stopped waiting. Partial tool-call data is never returned as an accepted action.

This avoids replaying ambiguous or partially delivered model output and prevents duplicate action execution.

## 3. Stream protocol telemetry

The SSE consumer and Cloudflare provider diagnostics now record bounded metadata:
- stream event count;
- output characters;
- reasoning characters;
- tool-call delta count;
- terminal `[DONE]` sentinel observed;
- finish reason;
- stable stream parser error code;
- fallback enabled / attempted / succeeded;
- fallback reason;
- fallback attempts used and maximum;
- actual HTTP attempt count.

No raw reasoning text, model output, SSE frames, credentials, or provider-controlled error bodies are written to published telemetry.

The investigator carries safe per-round provider diagnostics into `provider_round_telemetry`. The report distinguishes:
- model requests attempted;
- provider responses received;
- provider responses failed;
- accepted model actions.

A provider request attempt is not counted as a received response, and a received response is not automatically counted as an accepted action.

## 4. Live workflow configuration

The main live-evaluation workflow explicitly sets:
- Cloudflare: `FEA_LLM_STREAM_FALLBACK=true`;
- Cloudflare: `FEA_LLM_STREAM_FALLBACK_MAX_ATTEMPTS=1`;
- other providers: fallback disabled and maximum attempts zero.

The workflow retains:
- SSE streaming for Cloudflare;
- `medium` reasoning effort;
- one normal transport attempt for streaming requests;
- existing provider secrets isolation;
- validation-gate prerequisite and exact source SHA pinning;
- smoke-gate v3 and all N7.2 acceptance checks.

The fallback is an additional bounded HTTP request, not an investigation round or a tool call.

## 5. Investigation budget reconciliation

The actual N7.2 live configuration is:
- 11 maximum graph model rounds;
- 12 maximum evidence-tool calls;
- 3 finalization rounds reserved;
- 2,048 completion tokens per graph call;
- 180,000 cumulative token budget;
- 900-second elapsed-time ceiling.

Earlier N7.2 documentation described 11 tool calls and two finalization rounds. N7.3 corrects that documentation mismatch without changing the validated runtime configuration.

The single process-wide stream fallback adds at most one additional HTTP request per provider instance. It does not increase model rounds, evidence-tool calls, or the configured per-call token ceiling.

The existing investigation `max_cost_usd` control remains available when a conservative estimator is supplied. The live workflow does not currently supply a provider pricing estimator, so N7.3 does not claim a dollar-denominated cost ceiling. The one-fallback cap is the explicit additional-request bound.

## 6. Acceptance tests

New deterministic tests cover:
- incomplete stream with zero meaningful output followed by successful non-streaming recovery;
- native response-tool fallback returning inert data only;
- no fallback after partial content;
- no fallback after reasoning-only output;
- no fallback after a partial tool-call delta;
- process-wide fallback cap of one even if configuration requests more;
- fallback attempt and outcome diagnostics;
- attempted-versus-received provider-round accounting.

Existing tests continue to cover:
- read-timeout non-replay;
- interrupted partial-stream non-replay;
- malformed native tool-call rejection;
- reasoning-content preservation and privacy;
- strict local response normalization and action validation;
- N7.2 retry-aware discovery aggregation and target-specific context contract.

## 7. Changed files

### Stage1 — `stage1/section-uuids`

- `providers/cloudflare.py`
- `audit_engine/semantic_audit/ae32c/investigator.py`
- `tests/test_cloudflare_native_tool_calls.py`
- `tests/semantic_audit/test_ae32c_patch4_incident_evaluation.py`
- `docs/audit-engine/AE-32C-E7R3N7.2-Retry-Aware-Qwen-Reasoning-Continuity.md` (corrected budget description)
- `docs/audit-engine/AE-32C-E7R3N7.3-Cloudflare-Stream-Resilience.md` (new)

### Main — live-evaluation control plane only

- `.github/workflows/ae32c-live-evaluation.yml`
- `tools/tests/test_ae32c_validation_gate_workflows.py`
- `docs/audit-engine/AE-32C-live-evaluation-workflow.md`

No G9.42 profile, Manual Validation Dispatcher implementation, application code on `main`, Cloudflare endpoint, Qwen model, reasoning effort, or runtime execution permission is changed.

## 8. Research basis and limitations

The implementation direction was informed by:
1. Cloudflare Workers AI Qwen3.8-27B documentation:  
   https://developers.cloudflare.com/workers-ai/models/qwen3.8-27b/
2. Cloudflare Workers AI provider changelog, including stream termination and non-streaming fallback reliability improvements:  
   https://github.com/cloudflare/ai/blob/main/packages/workers-ai-provider/CHANGELOG.md
3. Cloudflare AI Gateway retry documentation:  
   https://developers.cloudflare.com/ai-gateway/configuration/retries/
4. Qwen3.8 official model card:  
   https://huggingface.co/Qwen/Qwen3.8-27B
5. Qwen3.8 premature-EOS issue report #55420:  
   https://github.com/QwenLM/Qwen3.8/issues/55420
6. Qwen3.8 tool-calling report #236:  
   https://github.com/QwenLM/Qwen3.8/issues/236
7. Qwen3.8 streaming report #55284:  
   https://github.com/vllm-project/vllm/issues/55284
8. OpenAI Python SDK error handling and streaming guidance:  
   https://github.com/openai/openai-python#retries

The issue reports concern different serving stacks and do not prove a Cloudflare Qwen3.8 defect. The package treats them as failure-mode references only.

## 9. Live acceptance requirements

The next controlled live evaluation must establish:
1. A complete SSE response is accepted with terminal metadata.
2. A zero-output incomplete SSE response can recover through at most one non-streaming request.
3. A partial content, reasoning, or tool-call stream is never replayed.
4. A failed fallback terminates safely and is reported distinctly.
5. The fallback request preserves the same model, prompt, tool schema, token cap, and reasoning configuration.
6. The investigator distinguishes attempted requests, received responses, failed responses, and accepted actions.
7. All required discovery operations complete.
8. Required source evidence and final direct citations resolve.
9. Retry-aware discovery remains intact.
10. Raw reasoning and raw SSE data remain absent from published artifacts.
11. Full G9.42, full repository regression, evidence digest verification, and provenance verification pass on the exact new Stage1 commit before any live provider request.

No live provider request is made during package construction.
