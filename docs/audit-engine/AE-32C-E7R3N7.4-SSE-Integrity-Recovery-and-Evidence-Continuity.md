# AE-32C E.7-R.3N.7.4 — SSE Integrity, Bounded Recovery and Evidence Continuity

**Status:** Corrective implementation prepared; GitHub validation pending  
**Target Stage1 branch:** `stage1/section-uuids`  
**Expected Stage1 base:** `bdcf3a3d543a3f58a20a0c14a2f0f659e90c8916`  
**Expected main base:** `9dc88b0360bed071256f2a5baa6f59454be98674`  
**Triggering live run:** `43927990295`  
**Triggering G9.42 run:** `43925224645`  
**Model:** `@cf/qwen/qwen3.8-27b`

## 1. Evidence that motivated N7.4

The N7.3 live evaluation used Stage1 commit `bdcf3a3d543a3f58a20a0c14a2f0f659e90c8916`, validated by G9.42 run `43925224645`. The main workflow commit was `9dc88b0360bed071256f2a5baa6f59454be98674`.

The baseline streamed successfully: 1,686 events, 3,418 reasoning characters, 3,741 output characters, `finish_reason=stop`. The graph-assisted condition completed seven provider responses, then failed on request eight. Its last request returned HTTP 200 and reported:

- 516 complete SSE events parsed;
- 1,862 partial reasoning characters;
- zero content characters;
- zero tool-call deltas;
- no terminal `[DONE]` sentinel;
- no finish reason;
- `malformed_stream_event` / `StreamProtocolError`;
- one HTTP attempt and no fallback.

The graph run stopped at round eight; finalization was scheduled to start at round nine. Ten evidence-tool calls completed and the required source reads/context discovery were complete, but the run produced no final source references and no accepted citations. The raw malformed SSE frame was not retained, so the exact upstream wire defect remains unknown.

## 2. Confirmed parser weakness and correction

The N7.3 parser consumed each `data:` line and immediately JSON-decoded that individual line. It did not accumulate multiple `data:` fields into one SSE event. This conflicts with the SSE event processing model, where data fields in an event are joined with newline characters and the event is dispatched at a blank-line boundary.

N7.4 replaces this with a bounded incremental parser over `Response.iter_content()`:

- reads raw transport chunks once;
- checks pending line size while bytes arrive;
- handles CRLF, LF and CR line endings, including boundaries split across chunks;
- decodes completed lines as strict UTF-8;
- strips one leading UTF-8 BOM;
- ignores comment lines;
- parses SSE fields and accumulates multiple `data:` values;
- dispatches only on blank-line event boundaries;
- joins multiple data fields with `\n` before JSON decoding;
- discards an unterminated pending event at EOF;
- recognizes usage-only chunks with an empty `choices` array;
- validates event, choice, delta, content and tool-call field types;
- applies line, event, wire, event-count and assembled-response limits.

The parser does not retain raw event bodies. It records only event index, byte length, SHA-256 fingerprint, JSON decoder position and a bounded set of response headers.

## 3. Recovery policy

N7.3 correctly refused to replay partial content and partial tool-call output. Its restriction also prevented recovery after reasoning-only output. N7.4 introduces an explicit opt-in for that narrow case.

`FEA_LLM_STREAM_FALLBACK_ALLOW_REASONING_ONLY=true` permits one non-streaming recovery only when:

- the failure is a classified SSE protocol or schema error;
- zero user-facing content characters were received;
- zero tool-call deltas were received;
- no action was accepted or executed from the failed response;
- the provider-instance fallback allowance remains available;
- the investigation's token and monetary cost reservation permits the request.

Partial reasoning is discarded and is not included in the recovery prompt. The fallback reissues the original logical messages and request settings with `stream=false`. It does not resume or continue from partial reasoning.

No fallback is allowed after any user-facing content or any tool-call delta. Read timeouts and interrupted transport streams remain non-replayable. The maximum remains one fallback request per provider instance.

The new flag defaults to false in the provider. The main live workflow must explicitly set it to true for Cloudflare and false for other providers; the exact insertion snippet is supplied in `MAIN_BRANCH/WORKFLOW_ENVIRONMENT_PATCH.md`.

## 4. Response transaction and investigation continuity

Provider output remains uncommitted until a complete response has been assembled and passes existing response normalization. Partial SSE data is diagnostic only. The provider adapter never executes a tool call; existing investigator validation remains the only path to dispatch.

The investigator report now includes `investigation_continuity` with:

- provider requests attempted, responses received and responses failed;
- accepted model action count;
- evidence ledger entry count;
- whether verified evidence remained in the ledger after provider failure;
- an explicit `partial_provider_response_accepted=false` invariant;
- whether finalization started;
- finalization eligibility based on verified snapshot, complete required source reads and complete required context contract.

A provider failure does not fabricate a final diagnosis or citations. It leaves the investigation incomplete, preserves evidence already committed to the ledger, and reports whether finalization prerequisites had been satisfied. Final citations remain mandatory and are not waived.

## 5. Diagnostics

New bounded metadata includes:

- stream event count and last parsed event index;
- error event index;
- malformed payload byte length and SHA-256 fingerprint;
- JSON decoder error position;
- content type, content encoding and transfer encoding from an allowlist;
- validated Cloudflare `CF-Ray` identifier;
- partial content, reasoning and tool-call delta counters;
- terminal sentinel and finish reason;
- fallback enabled, reasoning-only eligibility, attempted/succeeded and reason.

Raw reasoning, raw SSE payloads, credentials and provider-controlled error bodies remain excluded from published reports. Top-level and per-round diagnostic fields use the same definitions and allowlists.

## 6. Monetary cost reservation

N7.4 activates the existing investigator cost-reservation mechanism for Cloudflare Qwen3.8-27B.

Default total live-evaluation estimate ceiling: **USD 0.50** (`FEA_AE32C_MAX_COST_USD`). The baseline request's conservative estimate is reserved first; the remaining allowance is passed to the graph-assisted investigation.

Published Cloudflare rates used as defaults at package preparation:
- input: USD 0.45 per million tokens;
- output: USD 3.20 per million tokens.

The estimator:
- converts prompt characters to estimated tokens using `ceil(chars / 4 * 1.25)`;
- does not assume cached-input discounts;
- reserves two maximum output allowances to cover one possible recovery request;
- adds a 15% uncertainty margin;
- accepts operator overrides through `FEA_AE32C_CLOUDFLARE_INPUT_USD_PER_M` and `FEA_AE32C_CLOUDFLARE_OUTPUT_USD_PER_M`.

This is a conservative application-side reservation model, not a guarantee of provider billing or a substitute for account-level Cloudflare spending controls. Provider-reported cost is separately reported when available. The estimator is enabled only for the exact Cloudflare Qwen3.8-27B model; other provider/model combinations retain their existing configuration.

## 7. Finalization and citation rules

The investigation may enter finalization only after its existing required-source-read and required-context contracts are complete and the source snapshot is verified. The final diagnosis must still cite the required source paths directly. N7.4 does not count a source read as a citation and does not allow finalization to bypass missing source evidence.

If provider recovery fails, the run remains incomplete. The continuity report explains whether finalization prerequisites were already satisfied and preserves the ledger for review.

## 8. Acceptance tests

New deterministic tests cover:
- multiple `data:` fields assembled into one JSON event;
- UTF-8 BOM and CRLF handling;
- UTF-8 code points split across transport chunks;
- usage-only chunks with empty `choices`;
- invalid content field types and unexpected content type;
- unterminated final event discarded at EOF;
- malformed JSON after reasoning-only deltas with one bounded non-streaming recovery;
- reasoning-only recovery disabled unless explicitly enabled;
- no replay after partial content or partial tool-call deltas;
- error fingerprint and decoder position without raw payload retention;
- finalization eligibility and evidence preservation after provider failure;
- Cloudflare Qwen cost estimator and invalid price/ceiling rejection.

Existing G9.42 and N7.3 recovery, discovery, action-normalization, evidence and citation contracts remain in force.

## 9. Research references

1. WHATWG HTML Standard — Server-Sent Events: https://html.spec.whatwg.org/multipage/server-sent-events.html
2. Python Requests API — `iter_content` and `iter_lines`: https://docs.python-requests.org/en/stable/api/
3. Python Requests advanced streaming guide: https://docs.python-requests.org/en/latest/user/advanced/
4. Cloudflare Qwen3.8-27B model page and current unit pricing: https://developers.cloudflare.com/workers-ai/models/qwen3.8-27b/
5. Cloudflare Workers AI pricing: https://developers.cloudflare.com/workers-ai/platform/pricing/
6. Cloudflare AI Gateway retries: https://developers.cloudflare.com/ai-gateway/configuration/retries/
7. Cloudflare Workers AI provider changelog: https://github.com/cloudflare/ai/blob/main/packages/workers-ai-provider/CHANGELOG.md

The SSE standard is normative for event framing. Requests documentation supports using raw chunk iteration and explains that `iter_lines()` is not reentrant-safe. Cloudflare pricing is time-sensitive; package defaults are operator-overridable. Provider issue reports from other models/serving stacks are contextual only and do not prove the root cause of the N7.3 incident.

## 10. Explicit exclusions

- No generic retry increase or AI Gateway retry policy.
- No replay after partial content or tool-call deltas.
- No resumption using partial reasoning text.
- No tool execution inside the provider adapter.
- No changes to G9.42 profile, Manual Validation Dispatcher or smoke-gate v3.
- No changes to model ID or reasoning effort (`medium`).
- No weakening of required source citation or provenance gates.
- No raw reasoning or raw malformed SSE payloads in published artifacts.
