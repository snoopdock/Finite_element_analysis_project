# AE-32C E.7-R.3N.5 — Provider Latency and Streaming Diagnostics

**Status:** locally tested corrective proposal; GitHub acceptance and live-provider behavior are pending.
**Target source branch:** `stage1/section-uuids`
**Related validated source commit:** `4e290c3ceb680d0332c989a321dbef7035f631d0`
**Related G9.42 run:** `43580436638`
**Related Cloudflare preflight:** `43580669759`
**Related failed live evaluation:** `43580845255`

## 1. Evidence motivating this increment

The supplied records show:

- G9.42 accepted the prior source commit.
- Cloudflare Qwen preflight succeeded for ordinary transport, native response-tool output, and plain-text output.
- The subsequent full-context live evaluation failed in both baseline and graph-assisted conditions.
- Both live conditions used the OpenAI-compatible Chat Completions endpoint after E.7-R.3N.4.
- The baseline request took about 100.11 seconds and the graph request about 100.161 seconds, with two HTTP attempts and a 45-second read timeout per attempt.
- The graph prompt was approximately 16,085 characters / 4,022 estimated input tokens and reserved an 8,000-token completion cap.
- No model response content was received in either timed-out condition.

This establishes a workload/latency problem after transport compatibility was achieved. It does **not** prove whether the cause was time-to-first-token, model reasoning time, provider queueing, endpoint load, or another provider-side condition. The prior non-streaming request path did not expose time-to-first-output telemetry.

## 2. Changes in this increment

### 2.1 Streamed Cloudflare Chat Completions

The Cloudflare adapter can now request SSE streaming for OpenAI-compatible chat calls. The `stream` request parameter is enabled by the main-branch preflight and live-evaluation workflows for Cloudflare. The adapter requests `text/event-stream` and consumes the response incrementally.

The SSE parser:

- accepts only choice index `0` and one virtual response-tool call;
- reassembles streamed function name and argument fragments;
- bounds event count, wire payload size, and normalized output characters;
- requires `[DONE]` or a terminal `finish_reason`;
- preserves `finish_reason="length"` so the canonical response normalizer can reject a truncated action and use the existing bounded response-mode downgrade;
- rejects malformed, incomplete, oversized, multi-choice, or multi-tool streams;
- never dispatches a tool call.

The parser uses `iter_lines(chunk_size=128)` to avoid unnecessarily buffering large chunks before observing an event.

### 2.2 Separate connect and read-inactivity timeouts

Cloudflare requests now use a `(connect_timeout, read_timeout)` tuple:

- connect timeout: 10 seconds;
- read-inactivity timeout: 90 seconds.

The Requests library defines the read timeout as the maximum interval waiting between bytes, not a total wall-clock cap. Streaming can therefore continue beyond 90 seconds if the provider keeps sending data. The investigation-level wall-clock budget remains independently bounded.

A read timeout or interrupted response stream is ambiguous because provider execution may already have occurred. The adapter therefore does not automatically replay that POST. It records the failure and any partial output length. For this streamed Cloudflare experiment, the investigator disables its extra transport retry as well, so baseline and graph use one HTTP attempt per logical request. Non-streaming Cloudflare and NaraRouter retain their existing separate bounded retry policy.

### 2.3 Bounded generation and reasoning effort

The main-branch workflows set `FEA_LLM_REASONING_EFFORT=medium` for Cloudflare. The adapter sends `reasoning_effort` only for the exact Qwen 3.8 27B model ID; other Cloudflare models do not receive this model-specific parameter.

The live graph condition's per-call completion cap is reduced from 8,000 to 2,048 tokens. The baseline cap remains 2,000 tokens. The graph investigation wall-clock budget is 900 seconds, bounded by the live workflow's 22-minute job timeout.

These are controlled experimental settings, not claims that lower reasoning or token caps necessarily improve diagnostic quality. A `finish_reason="length"` result is explicitly surfaced rather than silently treated as complete.

### 2.4 Timing and failure telemetry

The adapter records bounded, non-sensitive diagnostics:

- elapsed request time;
- time to first SSE event;
- time to first visible content or function-argument output;
- stream event count;
- output and partial-output character counts;
- connect/read timeout settings;
- attempt count;
- streaming flag;
- reasoning effort and completion cap;
- finish reason;
- sanitized error type/category.

The provider preflight, baseline comparison, and graph report expose only an allowlisted subset. Raw prompts, response bodies, credentials, and reasoning text are not copied into the diagnostics.

## 3. Provider independence boundary

This increment changes the Cloudflare transport adapter and the shared evaluation telemetry only. It does not create a Qwen-specific investigator.

The following remain common and authoritative:

- response normalization;
- canonical AE-32C action schema;
- tool allowlist and argument validation;
- evidence ledger and source-reference verification;
- token, prompt, call, time, and finalization budgets;
- final diagnosis and citation validation.

Other providers can implement streaming and equivalent timing diagnostics in their own thin adapters without changing investigation semantics.

## 4. Workflow settings

For Cloudflare Qwen, the main-branch workflows now set:

```text
FEA_LLM_STREAMING=true
FEA_LLM_CONNECT_TIMEOUT_SECONDS=10
FEA_LLM_REQUEST_TIMEOUT_SECONDS=90
FEA_LLM_RETRY_ATTEMPTS=1
FEA_LLM_REASONING_EFFORT=medium
```

The exact model override for this experiment is:

```text
@cf/qwen/qwen3.8-27b
```

The investigator may grant one bounded retry for a connection-establishment failure on its first Cloudflare call. The adapter never replays a request after an ambiguous read timeout or an interrupted response stream.

## 5. Validation status

Local verification on Python 3.13:

- G9.42 targeted selection: **356 passed**.
- Focused modified-file tests: **113 passed**.
- Python compilation of all modified Python files: passed.
- YAML parsing of both changed GitHub workflow files: passed.
- Full repository regression: **incomplete**. The local execution window expired while running the unrelated `tests/semantic_audit/test_ae03_evolution.py::test_test_edit_invalidates_report`; no full-suite pass is claimed.

The package has not been run against Cloudflare live inference. GitHub G9.42 and streamed provider preflight are required after manual upload.

## 6. Acceptance sequence

1. Upload Stage1 files and commit.
2. Upload the two workflow files to `main`.
3. Run G9.42 against the exact new Stage1 commit.
4. Run Cloudflare provider preflight using `@cf/qwen/qwen3.8-27b`.
5. Confirm all three probes report `streaming=true` and inspect time-to-first-event/output.
6. Only after preflight passes, run one bounded live evaluation.
7. Compare baseline and graph request telemetry, finish reasons, output lengths, evidence coverage, citations, and final diagnosis.

A successful streaming preflight is not evidence of a successful full investigation. Diagnostic correctness remains unassessed until the final report is independently reviewed.

## 7. External technical references

- Cloudflare Qwen 3.8 27B model documentation: https://developers.cloudflare.com/workers-ai/models/qwen3.8-27b/
  - Documents the OpenAI-compatible Chat Completions endpoint, `stream`, `max_completion_tokens`, `reasoning_effort` (`low`, `medium`, `high`), and SSE streaming response format.
- Requests advanced usage: https://requests.readthedocs.io/en/latest/user/advanced/
  - Documents `stream=True`, `Response.iter_lines()`, and separate connect/read timeouts.
  - Clarifies that the read timeout is the interval waiting between bytes, not a total request wall-clock timeout.
