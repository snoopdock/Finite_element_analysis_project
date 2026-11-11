# AE-32C E.7-R — Provider-Independent Response Normalization

**Status:** Implementation prepared; focused regression suite passed; G9.42 validation and live Qwen preflight remain pending.

## 1. Purpose

Separate provider/model output formatting from the AE-32C investigation protocol.

Providers may return strict JSON, fenced JSON, JSON embedded in explanatory text, or an explicitly labelled text response. AE-32C deterministically normalizes supported representations into one canonical action object. Existing action, tool-argument, evidence, citation, finalization, budget, and state-machine validators remain authoritative.

The normalizer does not infer a tool invocation from unlabelled prose. Ambiguous output is rejected and consumes the existing bounded invalid-output recovery budget.

## 2. Naming and roadmap boundary

The supplied Pass 6 roadmap already uses **E.7** for claim-to-evidence quality. To avoid silently overwriting that accepted milestone, this response-normalization increment is labelled **E.7-R** (response normalization). The original claim-to-evidence workstream remains reserved and is not changed by this package. The project owner may formally revise milestone numbering in a later roadmap commit.

## 3. Normalization strategy order

1. `strict_json`: parse one complete JSON object with duplicate-key and non-standard-constant rejection.
2. `fenced_json`: parse one complete JSON object inside one Markdown code fence.
3. `labelled_text`: parse an explicit `ACTION` / `TOOL` / `ARGUMENTS` / `REASON` tool envelope, or `ACTION` / `DIAGNOSIS` final envelope. The argument/diagnosis payload itself remains strict JSON.
4. `embedded_json`: extract one unambiguous balanced JSON object from surrounding prose.
5. Reject: malformed, ambiguous, oversized, duplicate-key, unknown, or unlabelled natural-language responses are not converted into actions.

The order gives explicit labelled action syntax precedence over a JSON object embedded in its argument or diagnosis field. More than one independent JSON object is ambiguous and is rejected.

## 4. Canonical protocol and safety boundary

The normalizer only returns a dictionary. It does not call tools, validate tool permissions, resolve evidence IDs, accept source citations, or finalize a diagnosis.

After normalization, the existing investigator performs its normal checks:
- exact action envelope and allowed action name;
- registered read-only tool allowlist and exact argument schema;
- bounded action and retry budgets;
- source path and line-range constraints;
- evidence-ledger membership and provenance;
- finalization-only restrictions;
- diagnosis schema and evidence-completeness validation.

A finalization round still permits only the `final` action. A labelled text response cannot bypass that restriction.

Provider-controlled response text is never copied into reports, diagnostics, or recovery feedback. The report records only the normalization strategy, whether surrounding text existed, and safe error categories/positions.

## 5. Important limitation: arbitrary prose is not safely machine-interpretable

No deterministic parser can reliably infer all possible tool names, arguments, evidence IDs, or diagnosis fields from arbitrary unlabelled prose. Treating any sentence such as "search for total_calls" as an executable request would bypass the explicit action contract and could invent missing arguments.

Accordingly, this implementation accepts common response containers and a simple explicit labelled fallback. If the model produces unlabelled prose, the response is rejected and the bounded recovery prompt asks for one of the supported formats. A future model-mediated semantic translation pass would be a separate component with its own cost, trust boundary, provenance, validation, and failure budget; it is not silently included here.

## 6. Web research findings (reviewed 11-Nov-2026)

### 6.1 Cloudflare Workers AI JSON Mode

Cloudflare's JSON Mode documentation describes `response_format` with `json_object` or `json_schema`, and requires a valid JSON Schema for schema mode. Its published supported-model list includes selected Llama models, Hermes, DeepSeek Coder, and DeepSeek R1 Distill Qwen 32B. It does **not** list `@cf/qwen/qwen3.8-27b` in that allowlist. Cloudflare also warns that even supported models may fail to satisfy a complex schema, returning `JSON Mode couldn't be met`; JSON Mode does not support streaming.

Source: https://developers.cloudflare.com/workers-ai/features/json-mode/

### 6.2 Qwen 3.8 27B capabilities

Cloudflare's Qwen model page identifies `@cf/qwen/qwen3.8-27b` as supporting function calling, reasoning, vision, and batch. Its API parameter reference includes `tools`, `tool_choice`, `parallel_tool_calls`, `reasoning_effort`, `response_format`, and `max_completion_tokens` (with `max_tokens` marked deprecated).

Sources:
- https://developers.cloudflare.com/workers-ai/models/qwen3.8-27b/
- https://developers.cloudflare.com/workers-ai/features/function-calling/
- https://developers.cloudflare.com/workers-ai/features/function-calling/traditional/

Cloudflare's traditional function-calling documentation shows a request containing named tools and parameter schemas, followed by a structured `tool_calls` response with tool name and arguments. This is a better future fit for AE-32C tool actions than forcing the model to author an entire JSON action envelope, because the application still validates the selected tool and arguments before dispatch.

Important repository distinction: the supplied AE-32C Cloudflare adapter currently declares `native_tool_calls: false` and its chat extraction path returns text. The model's advertised function-calling capability is therefore not yet exposed by the local adapter. This package does not change that capability declaration or claim native tool-call support. A future adapter increment should capture and validate the native response envelope before declaring support.

### 6.3 Workers SDK issue #16165

The linked issue was opened on 9-Oct-2026 and is marked as an open Workers AI bug in the retrieved issue view. The report describes Qwen 3.8 27B timing out with error 3046 after roughly 120 seconds for a particular request using `response_format: {type: "json_schema"}` together with `reasoning_effort: "low"`. In the reported test matrix, medium or omitted reasoning effort, `json_object`, and no `response_format` completed for that example.

Source: https://github.com/cloudflare/workers-sdk/issues/16165

This issue supports avoiding dependence on Qwen's JSON-Schema constrained mode for the initial integration. It does **not** directly explain the previous AE-32C preflight failure: that preflight used ordinary chat with local strict parsing, not `json_schema` plus low reasoning effort. The issue is a separate documented risk, not proof of the cause of the invalid JSON response.

### 6.4 Cloudflare Browser Run `/json` endpoint

The Browser Run `/json` Quick Action extracts structured data from a webpage. It accepts a `url` or `html` input and either a prompt or JSON-schema `response_format`. The default extraction model is `@cf/meta/llama-3.3-70b-instruct-fp8-fast`; `custom_ai` can select supported provider/model entries with BYO authorization and ordered fallbacks.

Sources:
- https://developers.cloudflare.com/browser-run/quick-actions/json-endpoint/
- https://developers.cloudflare.com/browser-run/quick-actions/

This is not a general-purpose completion-normalization API. Using it as an intermediary for repository-investigation responses would add a second model/service, additional credentials and data routing, latency/cost, and another untrusted output. It is not part of the E.7-R runtime design.

### 6.5 Established structured-output design patterns

Pydantic AI documents native, tool-based, and prompted output strategies, with validation and bounded retries. LangChain similarly distinguishes provider-native structured output from tool-based strategies and selects based on provider/model capabilities.

Sources:
- https://ai.pydantic.dev/output/
- https://docs.langchain.com/oss/python/langchain/structured-output

The design lesson adopted here is to separate capability selection, parsing, validation, and bounded recovery. This implementation does not add either framework as a runtime dependency.

## 7. Provider expansion plan

The normalizer API is provider-independent because it consumes response text, not provider-specific request objects. The same implementation can be used by Cloudflare, OpenRouter, and other text-returning adapters.

Recommended rollout:
1. Cloudflare Qwen: use the labelled fallback and JSON-container normalization; run the Qwen compatibility preflight after G9.42.
2. Cloudflare native tool-call adapter: separately implement and test the model's documented function-calling response shape; only then declare `native_tool_calls` true for the exact adapter/model pair.
3. OpenRouter: run the same normalizer tests against Nemotron and any future selected model; do not infer capability from OpenAI compatibility.
4. Other providers: opt in only after adapter-envelope tests and provider/model-specific capability verification.

## 8. Validation and rollout gates

- Unit tests cover strict JSON, fenced JSON, one embedded object, explicit labelled text, ambiguous multiple objects, duplicate JSON keys, non-standard constants, oversized responses, duplicate labelled fields, and non-echo of rejected content.
- Investigator integration test proves a labelled tool response enters the existing tool-validation path and produces the same canonical action.
- Existing investigator, operational-failure, E.6 compatibility, incident-evaluation, and provider tests remain green in the focused local run.
- No live provider calls were made.
- No model default, provider routing, token budget, retry limit, evidence policy, acceptance threshold, or GitHub workflow is changed.

Next:
1. Compare the included investigator patch against the current successful Stage1 HEAD.
2. Upload the new normalizer module, investigator integration, tests, and this design record to `stage1/section-uuids`.
3. Run G9.42 against that exact commit.
4. Only after G9.42 passes, run the provider preflight for `@cf/qwen/qwen3.8-27b` using the updated Stage1 validation run ID.
5. Review the preflight artifacts before authorizing any live investigation or round-robin trial.

## 9. Explicit non-claims

A successful normalization test does not prove:
- Qwen follows the labelled response contract reliably;
- the Cloudflare adapter exposes native tool calling;
- a normalized diagnosis is accurate;
- a provider's citations semantically support its claims;
- a provider is ready for round-robin evaluation.

Those require their own validation and empirical gates.
