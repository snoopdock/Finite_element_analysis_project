# AE-32C E.7-R.3N.7.2 --- Retry-Aware Discovery and Qwen Reasoning Continuity

**Status:** Corrective implementation prepared; GitHub validation
pending\
**Target Stage1 branch:** `stage1/section-uuids`\
**Expected Stage1 base commit:**
`c2ac6bf138e0e01d90731254e4fd03b6af20eb9b`\
**Expected main workflow base commit:**
`eb3ab744d546098385771677730996508008aa36`\
**Validation prerequisite:** Manual Validation Dispatcher, G9.42,
`profile` mode\
**Live provider:** Cloudflare Workers AI, Qwen3.8-27B

------------------------------------------------------------------------

## 1. Triggering evidence

Live evaluation `43838993389` showed:

-   First `trace_execution_context` request rejected with
    `argument_out_of_range` because `max_results=50`.
-   Second request for the same target succeeded with `max_results=30`,
    complete and non-truncated.
-   The required target contract recorded one successful trace and
    complete reads of `main.py` and `providers/factory.py`.
-   Aggregate discovery nevertheless remained `partial`, because the
    first failed attempt was allowed to poison the operation status.
-   The main-branch smoke gate also checked aggregate
    `trace_status.status == "completed"` for the exact-target check,
    rather than the target-specific completion contract.
-   The baseline call used 2,000 completion tokens and ended with
    `finish_reason=length`.

The failed attempt must remain in the audit history. The correction is
to recover the final status of the same logical operation after a
successful complete retry, not to erase or hide the failed attempt.

## 2. Retry-aware discovery aggregation

### 2.1 Logical query identity

Discovery attempts are grouped by logical query:

-   `trace_execution_context`: target and semantic graph depth define
    identity; `max_results` is a retry-tunable bound and is excluded.
-   `find_related_tests`: target/query/path define identity; result
    limit is excluded.
-   `discover_case_context`: semantic filter arguments define identity;
    result limit is excluded.

A successful result for a different target cannot satisfy the original
target's failed query.

### 2.2 Completion rule

A logical query is complete only when at least one invocation for that
same query returned:

-   invocation status `ok`;
-   a mapping result;
-   `coverage_status == "complete_for_query"`;
-   explicit `truncated is false`;
-   all required result-list fields with list values.

A failed or truncated attempt remains counted. If a later complete
result for the same query succeeds, the operation status becomes
`completed_with_retry`.

The report now exposes: - `failed_attempt_count`; -
`invalid_result_attempt_count`; - `successful_complete_call_count`; -
`truncated_successful_call_count`; - `any_attempt_truncated`; -
`recovered_after_retry`; - `final_operation_status`; - query count,
completed query count, and unresolved query count.

The `truncated` field describes unresolved final operation state.
Historical truncated attempts remain visible separately through
`any_attempt_truncated` and the per-call ledger.

### 2.3 Target-specific contract

The required context contract counts all attempts for the configured
target, including rejected attempts. It separately records: - attempt
count; - completed call count; - failed attempt count; -
recovered-after-retry flag; - final target status.

A retry for another target cannot satisfy this contract.

Static graph relationships are deduplicated when repeated successful
traces return the same relationship.

## 3. Smoke-gate v3

The main-branch live-evaluation workflow now uses:

`ae32c/live-smoke-gate/v3`

The exact-target trace check reads the target-specific required-context
contract:

-   contract enabled;
-   contract status `complete`;
-   required tool is `trace_execution_context`;
-   required target is `pipeline/extractor.py`;
-   target trace final status is `completed`;
-   target trace completed-call count is at least one.

The broader `investigation_context_discovery_complete` check remains
separate. It still requires all three discovery operations to be
complete and non-truncated. Thus a successful exact-target trace cannot
conceal an incomplete unrelated discovery query.

The smoke metrics preserve the aggregate trace call count,
failed-attempt count, final operation status, and recovered-after-retry
flag.

## 4. Baseline completion recovery

The one-shot baseline completion allowance increases from 2,000 to 4,096
tokens.

Constraints: - baseline remains one provider request; - no automatic
baseline retry is introduced; - graph investigation per-call completion
allowance remains 2,048 tokens; - total graph token budget remains
180,000; - baseline `finish_reason=length` continues to mean
`response_truncated` and cannot pass the smoke gate; - the comparison
transport report records the configured baseline completion allowance.

This is a bounded correction to the observed one-shot truncation, not a
claim that 4,096 tokens guarantees a complete response.

## 5. Qwen3.8 reasoning-context preservation

### 5.1 Provider response contract

`ProviderToolCall` and `ProviderResponse` gain an optional
`reasoning_content` field. The field is excluded from object
representations and equality comparisons to reduce accidental
disclosure.

The Cloudflare adapter: - extracts `reasoning_content` from
non-streaming assistant messages; - accepts the `reasoning` alias when
present; - accumulates `reasoning_content` or `reasoning` deltas during
OpenAI-compatible SSE streaming; - preserves reasoning content when a
native tool call is present; - returns an envelope carrying reasoning
content when a tool-mode response is text-shaped; - counts reasoning
content toward response-size limits; - records only bounded character
count and SHA-256 fingerprint in provider diagnostics.

The raw reasoning text is not written to: - the evidence ledger; -
diagnosis claims; - source citations; - comparison reports; - provider
statistics; - published smoke-gate artifacts.

### 5.2 Conversation continuity

When the investigator appends a normalized assistant action to transient
conversation history, it carries the optional `reasoning_content` field
separately from the canonical action JSON.

This lets Qwen3.8 retain its model-specific reasoning context across
tool turns without mixing that content into the evidence action or
diagnosis.

The reasoning field is included in the serialized conversation prompt
and therefore in the existing prompt/token budget accounting. If it
causes a budget limit to be exceeded, the existing admission gate
remains authoritative.

### 5.3 Qwen template configuration

For the Qwen3.8 model route, the Cloudflare request explicitly sends:

``` json
{
  "chat_template_kwargs": {
    "preserve_thinking": true
  }
}
```

This follows the Qwen3.8 model-card setting for preserving thinking
context. The adapter does not disable thinking.

The reasoning-effort allowlist accepts the union of documented
Cloudflare and Qwen3.8 values: `low`, `medium`, `high`, and `xhigh`. The
N7.2 live workflow continues to use `medium`; it does not change
reasoning effort during this comparison.

The Cloudflare model page and Qwen model card have different enumerated
reasoning-effort descriptions. N7.2 keeps `medium` for the live run and
treats `xhigh` support as configuration compatibility, not as an
assertion that the Cloudflare endpoint has been live-verified with
`xhigh`.

## 6. Bounded live-investigation allowance

The implemented live configuration is:

-   maximum graph model rounds: 11;
-   maximum graph evidence-tool calls: 12;
-   per-call graph completion allowance: 2,048 tokens;
-   cumulative graph token budget: 180,000;
-   finalization rounds reserved: 3;
-   baseline completion allowance: 4,096 tokens, one request only.

The N7.2 live configuration intentionally retains three finalization
rounds and a 12-call tool ceiling. Earlier wording in this document
incorrectly described 11 tool calls and two finalization rounds; N7.3
corrects that documentation mismatch without changing the validated
runtime limits. Tool schemas, argument validation, evidence verification,
and truncated-result rules remain strict.

## 7. Research basis and limitations

The following external documentation and reports informed the
implementation:

1.  Cloudflare Workers AI Qwen3.8-27B model documentation:\
    https://developers.cloudflare.com/workers-ai/models/qwen3.8-27b/
2.  Official Qwen3.8-27B model card, including reasoning-content and
    `preserve_thinking` guidance:\
    https://huggingface.co/Qwen/Qwen3.8-27B
3.  Cloudflare LangChain integration changelog, including
    reasoning-content preservation fixes when tool calls coexist:\
    https://github.com/cloudflare/ai-utils/blob/main/packages/langchain/CHANGELOG.md
4.  Cloudflare AI Gateway retry documentation:\
    https://developers.cloudflare.com/ai-gateway/configuration/retries/
5.  Cloudflare issue #560, forced tool-choice behaviour:\
    https://github.com/cloudflare/ai/issues/560
6.  Cloudflare issue #561, required tool-call behaviour with long
    contexts:\
    https://github.com/cloudflare/ai/issues/561
7.  Qwen3.8 issue #236, long-prompt tool-calling observations with
    thinking disabled:\
    https://github.com/QwenLM/Qwen3.8/issues/236

The Cloudflare issue reports concern other models and/or serving
conditions and are treated as contextual risk signals, not proof of a
Qwen3.8 Cloudflare defect. The Qwen issue report concerns SGLang rather
than Cloudflare Workers AI. N7.2 does not add AI Gateway retries or
force tool selection: the observed N7.1 failure was an application-level
argument-validation/recovery problem, not a transient provider transport
failure.

## 8. Changed files

### Stage1 --- `stage1/section-uuids`

-   `providers/base.py`
-   `providers/cloudflare.py`
-   `audit_engine/semantic_audit/ae32c/investigator.py`
-   `audit_engine/semantic_audit/ae32c/live_evaluation.py`
-   `audit_engine/semantic_audit/ae32c/evaluation.py`
-   `audit_engine/semantic_audit/ae32c/provider_preflight.py`
-   `audit_engine/semantic_audit/ae32c/response_normalizer.py`
-   `tests/test_cloudflare_native_tool_calls.py`
-   `tests/semantic_audit/test_ae32c_provider_response_bridge.py`
-   `tests/semantic_audit/test_ae32c_patch4_incident_evaluation.py`
-   `docs/audit-engine/AE-32C-E7R3N7.2-Retry-Aware-Qwen-Reasoning-Continuity.md`
    (new)

### Main --- live-evaluation control plane only

-   `.github/workflows/ae32c-live-evaluation.yml`
-   `tools/tests/test_ae32c_validation_gate_workflows.py`
-   `docs/audit-engine/AE-32C-live-evaluation-workflow.md`

No G9.42 profile, Manual Validation Dispatcher implementation,
application code on `main`, provider endpoint, response-normalization
policy, or runtime execution permission is changed.

## 9. Acceptance tests

Package-build checks: - retry after `argument_out_of_range` completes
the same logical query; - failed-only query remains partial; - retry for
another target cannot satisfy the original target; - truncated success
remains partial; - tool-call and text-envelope reasoning content is
preserved transiently; - streaming reasoning deltas are accumulated; -
reasoning content is not emitted in stats or reports; - `high` and
`xhigh` reasoning-effort configuration values are accepted; - baseline
allowance is 4,096 and remains bounded; - exact G9.42 targeted profile
passes; - main live-workflow contract tests pass.

GitHub remains authoritative. Full repository regression and provenance
verification must pass on the exact new Stage1 commit before any live
provider request.

## 10. Live acceptance requirements

The next live run must demonstrate:

1.  If a trace call is rejected, the failure remains recorded.
2.  A complete retry for the same target yields `completed_with_retry`.
3.  A retry for a different target cannot satisfy the required target.
4.  Overall discovery reaches `completed` only when every required
    logical query has a complete, non-truncated result.
5.  The target-specific contract and aggregate discovery checks both
    pass.
6.  The baseline does not end with `finish_reason=length`.
7.  Qwen reasoning context is carried across tool turns when returned by
    Cloudflare.
8.  The raw reasoning content does not appear in evidence or published
    artifacts.
9.  Final citations resolve to the required direct source files.
10. Diagnostic accuracy remains subject to independent human review.

No live provider request is made during package construction.
