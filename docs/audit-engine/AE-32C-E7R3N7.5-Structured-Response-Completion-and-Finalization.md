# AE-32C E.7-R.3N.7.5 — Structured Response Completion and Finalization Reliability

**Status:** Corrective implementation prepared; GitHub validation and live acceptance pending  
**Baseline:** Stage1 `9e32d0eb4f8c5eb41f9fffcc407e3926d50ffb56`  
**Triggering live evaluation:** `44018302060`  
**Triggering validation:** `44017942317` (G9.42)

## 1. Triggering evidence

The N7.4 live evaluation passed its validation gate and completed ten provider requests. The SSE streams terminated normally and no provider transport failures were recorded. The graph investigation nevertheless stopped with `invalid_model_json`.

Three consecutive model responses ended with `finish_reason=length` while the configured completion allowance was 2,048 tokens. The first occurred during evidence gathering; two further invalid JSON responses occurred during finalization. The finalization policy allowed only one invalid-JSON retry even though three finalization rounds were reserved. After the first structured-response rejection, the investigator also downgraded the response representation to plain text, which did not address completion truncation.

The report retained the required source reads and evidence records, but no final source references or accepted citations were produced. This package does not weaken those requirements.

## 2. Implementation

### 2.1 Phase-specific completion allowance

- Evidence-gathering calls remain at 2,048 completion tokens for the Cloudflare Qwen3.8-27B live configuration.
- Reserved finalization calls use a separate 6,144-token completion allowance.
- The allowance is validated, included in prompt/token reservations, passed to the provider request, and reported separately.
- Other providers and non-live callers retain their existing per-call allowance unless they explicitly configure a finalization allowance.

### 2.2 Finalization provider profile

For Cloudflare `@cf/qwen/qwen3.8-27b` finalization calls only:

- Streaming is temporarily disabled; investigation and baseline streaming behavior are unchanged.
- Reasoning effort is temporarily set to `low`; evidence-gathering reasoning remains `medium` as configured.
- Provider attributes are restored after the request, including exception paths.
- The existing virtual `submit_ae32c_response` response function remains the preferred structured response channel. The adapter supplies exactly one virtual function, uses Qwen-compatible `tool_choice=auto`, and disables parallel tool calls. The function is data only and is never executed.
- Finalization instructions explicitly require the virtual response function when supplied. Local response normalization and evidence/action validation remain authoritative.

The package does not enable Cloudflare JSON Mode for Qwen3.8-27B. Model-specific compatibility is not inferred from generic OpenAI-compatible API support.

### 2.3 Truncation handling and recovery

- `finish_reason=length` is classified as generation truncation, not as proof that structured response mode is unsupported.
- The investigator retains the structured response channel after a length-truncated response rather than downgrading to unconstrained plain text.
- Finalization allows one initial response plus up to two bounded recovery responses across its three reserved rounds.
- Each recovery uses the larger finalization allowance and the same evidence-bound finalization context policy.
- Malformed provider output is not echoed into subsequent prompts. No rejected response is accepted as a completed diagnosis or dispatched action.
- If recovery is exhausted, the investigation remains incomplete; citation requirements are not relaxed.

### 2.4 Compact finalization output

The finalization prompt now asks for a concise evidence-bound diagnosis, preferring one root-cause statement and one claim, with at most three claims. It prohibits reproducing source code, long tool outputs, or a full narrative report. The existing diagnosis schema and source-reference validation remain unchanged.

The application continues to resolve evidence IDs, source references, source hashes and citation coverage against its authoritative ledger. This iteration does not replace the report renderer or alter the evidence ledger format.

### 2.5 Telemetry corrections

- A successful SSE `[DONE]` marker is no longer copied into fields named for malformed/error payload metadata.
- `accepted_model_action_count` now counts validated `tool_call` and `final_accepted` entries rather than every trace entry.
- Separate counters report model-action candidates, rejected actions, tool calls dispatched and tool calls completed.
- Finalization diagnostics report the phase-specific completion allowance and the finalization provider profile.

## 3. Monetary scope

No new monetary subsystem, pricing integration, or additional billing workflow is introduced. The existing N7.4 estimator and configured USD 0.50 ceiling are retained unchanged. The existing estimator receives the actual phase-specific completion reservation so the larger finalization allowance is not under-reserved. Provider-reported cost remains distinct from estimated cost.

## 4. Explicitly unchanged

- N7.2 retry-aware discovery and required context contract.
- N7.4 SSE parser, bounded reasoning-only recovery and no-replay boundaries.
- Evidence ledger, source snapshot verification and provenance checks.
- Direct source citation requirements and final citation acceptance.
- Tool authorization and local action validation.
- G9.42 profile, full regression requirement and smoke-gate v3.
- Qwen model identity and medium reasoning effort during baseline/evidence gathering.
- Existing USD 0.50 application-side estimate ceiling.

## 5. Acceptance criteria

1. G9.42 passes on the exact new Stage1 commit.
2. Full repository regression passes on GitHub Actions.
3. Evidence digest and provenance catalog verification pass.
4. Evidence-gathering calls remain at 2,048 tokens and medium reasoning.
5. Finalization requests use 6,144 completion tokens, non-streaming transport and low reasoning effort for the exact Cloudflare/Qwen model.
6. Provider attributes are restored after each finalization request.
7. A length-truncated response does not trigger an automatic plain-text downgrade.
8. Finalization has one initial request and at most two recovery requests.
9. The response tool remains inert data; no provider-supplied tool is executed without local validation and authorization.
10. All mandatory source citations resolve against the verified source snapshot.
11. SSE `[DONE]` is not reported as an error payload.
12. Accepted/rejected action and dispatched/completed tool counters reconcile.
13. Existing cost estimation and ceiling remain active without new monetary scope.
14. Any exhausted or invalid finalization remains explicitly incomplete.

## 6. Technical references

- Cloudflare Workers AI Qwen3.8-27B: https://developers.cloudflare.com/workers-ai/models/qwen3.8-27b/
- Cloudflare Workers AI function calling: https://developers.cloudflare.com/workers-ai/features/function-calling/
- Cloudflare Workers AI JSON Mode: https://developers.cloudflare.com/workers-ai/features/json-mode/
- Cloudflare OpenAI-compatible Chat Completions: https://developers.cloudflare.com/workers-ai/configuration/openai-compatibility/
- Qwen3.8-27B model card: https://huggingface.co/Qwen/Qwen3.8-27B

The model-specific tool-choice restriction is preserved: with Qwen thinking enabled, the adapter uses `auto` with exactly one virtual response function and `parallel_tool_calls=false`; it does not assume forced named-function selection or strict JSON Mode support.
