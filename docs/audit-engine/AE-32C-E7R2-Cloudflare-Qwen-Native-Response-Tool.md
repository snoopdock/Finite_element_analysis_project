# AE-32C E.7-R.2 — Cloudflare Qwen Native Response Tool

Status: implementation prepared; live Qwen behavior remains unverified until the manual preflight is run.

Source baseline:
- Repository: `snoopdock/Finite_element_analysis_project`
- Branch target: `stage1/section-uuids`
- Exact source archive commit: `75f7d0bbf47c21e526c37e474ba041eec00b1db7`
- Source archive SHA-256: `20d79a7d2a0f083461045263285f108a6b62e1213accdfd8de5d2ce952a106d1`

## 1. Why this increment exists

The earlier Qwen preflight used ordinary chat and required the model to emit a strict JSON action envelope. Cloudflare's Qwen 3.8 27B model page advertises function calling, but the model is not in the published Workers AI JSON Mode model list. Requiring plain chat to emit exact JSON therefore tested a weaker interface than the model documents.

Cloudflare references:
- Qwen 3.8 27B model page: https://developers.cloudflare.com/workers-ai/models/qwen3.8-27b/
- Traditional function calling: https://developers.cloudflare.com/workers-ai/features/function-calling/traditional/
- Workers AI Execute AI model REST API: https://developers.cloudflare.com/api/resources/ai/methods/run/
- OpenAI-compatible Chat Completions: https://developers.cloudflare.com/workers-ai/configuration/open-ai-compatibility/
- JSON Mode supported-model list: https://developers.cloudflare.com/workers-ai/features/json-mode/

The model page identifies `@cf/qwen/qwen3.8-27b` as supporting function calling. The traditional function-calling guide shows a tool definition with `name`, `description`, and `parameters`, and a returned `tool_calls` array containing `name` and `arguments`. The REST API schema for `/accounts/{account_id}/ai/run/{model_name}` explicitly accepts `tools` in that native shape and documents `result.tool_calls[]` in the response.

## 2. Transport decision

This increment deliberately keeps the existing Cloudflare `/ai/run/{model}` transport.

It does not migrate the adapter to `/ai/v1/chat/completions` just to obtain function calls. The existing `/ai/run` REST API explicitly documents:
- `tools` as an accepted TextGeneration input;
- native tool objects `{name, description, parameters}`;
- output `result.tool_calls[]` with `{name, arguments}`.

The OpenAI-compatible `/ai/v1/chat/completions` endpoint also documents `tools` and `tool_choice`, but this patch does not use it. The `/ai/run` REST schema does not document a `tool_choice` field for TextGeneration, so this patch does not send an undocumented `tool_choice`. It supplies one virtual response function and asks the model to call it; the preflight measures whether the selected Qwen endpoint actually does so.

`max_tokens` remains the request limit on `/ai/run`. The `max_completion_tokens` recommendation belongs to the OpenAI-compatible Chat Completions interface and is not substituted into this direct REST request.

## 3. Virtual response function

The common protocol defines one function:
- `submit_ae32c_response`

Its arguments carry the existing AE-32C action envelope. It is a response-format channel only:
- it is never executed;
- it does not expose repository tools to the provider adapter;
- it does not dispatch evidence operations;
- it cannot bypass the investigator's existing action, evidence, permission, or finalization validation.

For `tool_call`, the wrapper carries the exact registered tool name, arguments, and reason; `diagnosis` must be empty.

For `final`, the wrapper carries the complete diagnosis; `tool`, `arguments`, and `reason` must be empty values.

The normalizer converts this provider-native call into the existing canonical AE-32C JSON action. The investigator then applies its existing strict local validators.

## 4. Provider contract

`providers.base.ProviderToolCall` is a transport-neutral data object with `name` and `arguments`.

Cloudflare implements the optional method:
`chat_with_response_tool(messages, tool_definition=..., ...)`

The method:
1. accepts the common OpenAI-compatible function definition;
2. converts it to Cloudflare's documented native `/ai/run` tool shape;
3. sends exactly one response function;
4. parses exactly one returned `result.tool_calls` entry;
5. accepts arguments as an object or strict JSON string;
6. rejects duplicate keys, malformed arguments, multiple calls, and oversized argument payloads;
7. returns `ProviderToolCall` data or safe text fallback;
8. never executes the returned function.

The adapter declares native function-call support only when configured with the exact single model `@cf/qwen/qwen3.8-27b`. Mixed-model lists fail closed for this capability.

## 5. Capability scoping correction

The previous Cloudflare adapter declared `json_object_mode=True` for every configured model. The investigator consumes that capability declaration to decide whether to call `chat_structured`, so the generic declaration could cause unsupported models to be sent JSON Mode requests.

This patch makes Cloudflare JSON-object capability model-scoped to the published allowlist. Qwen declares:
- `native_tool_calls=True` at the adapter/model configuration level;
- `json_object_mode=False`.

This is a documented capability declaration, not proof that live calls will comply. The live preflight remains the behavior-verification gate.

## 6. Investigator integration

When the provider capability is enabled and the optional method exists, the investigator:
- inserts a short response-channel instruction after the primary system instruction;
- includes the virtual function definition in prompt/token reservation accounting;
- calls `chat_with_response_tool`;
- normalizes `ProviderToolCall` into the existing action envelope;
- sends the result through the unchanged tool/action/evidence validators.

Native response-function calls are not evidence-tool calls. A returned `tool_call` action during finalization is still rejected by the existing finalization gate before evidence-tool dispatch. The integration regression tests this explicitly.

If the provider does not return a native call but returns text, the existing deterministic text normalizer remains available. Ambiguous prose is not guessed into a tool invocation.

## 7. Preflight behavior

For exact Cloudflare model `@cf/qwen/qwen3.8-27b`, the manual preflight now:
1. performs the existing transport/sentinel call;
2. sends one virtual response function through the Cloudflare `/ai/run` tool interface;
3. requires one returned `submit_ae32c_response` call;
4. normalizes it locally;
5. verifies the canonical `repository_summary` dry-run action;
6. reports `tool_executed=false`.

The preflight does not call repository evidence tools. A plain text response, malformed call, unexpected function name, multiple calls, or schema mismatch fails the native-tool compatibility probe. Raw provider output and credentials are not persisted.

Other Cloudflare models retain the published JSON Mode allowlist path or ordinary-chat local validation. OpenRouter behavior is unchanged.

## 8. Security and limits

- No provider-native function is executed by the adapter.
- Only one virtual response function is accepted.
- Only one returned function call is accepted.
- Local normalization rejects unexpected envelope keys and contradictory action fields.
- The investigator still checks registered tool names and their argument schemas.
- Evidence IDs and source references remain validated against the existing evidence ledger.
- Finalization continues to prohibit evidence-tool dispatch.
- Raw provider response bodies and credentials are not written to preflight artifacts.
- Existing request timeout, retry, logical-call, token, context, and response-size limits remain in force.
- The serialized response-function schema is included in prompt/token reservation accounting.

## 9. Provider-independent extension

The optional `chat_with_response_tool` contract is intentionally generic. OpenRouter and future providers can implement the same method with their own wire shape. The common `ProviderToolCall` type, `response_protocol.py`, and `normalize_provider_tool_call` do not depend on Cloudflare's API response shape.

This increment does not yet add OpenRouter native function calling, runtime endpoint discovery, JSON Schema negotiation, or Response Healing. Those are separate increments after Qwen's live preflight succeeds.

## 10. Verification performed

Focused local suite on the exact supplied source archive with this patch applied:
- **264 passed**
- Python syntax compilation passed for all changed and added Python files.
- Tests cover Cloudflare tool request serialization, native response extraction, malformed and duplicate-key rejection, text fallback, model-scoped capabilities, preflight success/failure, canonical normalization, investigator integration, and finalization no-tool enforcement.

A full repository-wide `pytest -q` attempt was interrupted by the execution environment's 60-second automatic limit. Therefore this package does not claim a full repository regression or G9.42 pass. G9.42 must be run in GitHub against the new commit.

## 11. Acceptance sequence

1. Upload the listed files to `stage1/section-uuids`.
2. Run G9.42 against the exact commit.
3. If G9.42 passes, run Cloudflare Qwen preflight with `@cf/qwen/qwen3.8-27b`.
4. Require `native_tool_call_probe.status == "passed"` and `tool_executed == false`.
5. Only then run one bounded Qwen investigation.
6. After that investigation passes, implement the same optional provider response-tool contract in OpenRouter.
