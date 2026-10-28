# NaraRouter HTTP 400 — focused compatibility diagnostic plan

**Status:** Investigation plan; no root cause established.  
**Evidence source:** AE-32C live round-robin run `40503324230`, source commit `7c1e179a50583195fa464f97f7bd31a00c82032b`.

## Observed behavior

Across four rounds:

- Baseline: 0/4 completed; safe error code `provider_api_error_payload`; recorded error `nararouter HTTP 400`.
- Graph-assisted: 0/4 protocol-complete; each trial has its own provider-failure outcome with the same error code.
- The model is recorded as `agnes-2.5-flash`.
- Structured JSON mode was not requested because the adapter capability was recorded as unavailable or unverified.
- No valid completion envelope was observed.
- The logs do not preserve sufficient safe response structure to determine the precise HTTP 400 cause.

This establishes repeatable failure in this configuration, not whether the defect is in endpoint selection, model/API mode, request construction, provider configuration, or an intermediary.

## Required sequence

1. **Freeze the evidence.** Preserve the four baseline and four graph-side comparison artifacts, request metadata that is safe to retain, source commit, provider/model identifiers, and error classification. Do not add API keys, authorization headers, or raw secret-bearing payloads to fixtures.
2. **Inspect adapter configuration.** Verify the configured base URL/endpoint, model identifier, API mode, request headers, request body, and response-normalization contract against the provider's supported interface. Record the configuration source and its version without recording credentials.
3. **Build deterministic fixtures.** Add tests for at least:
   - HTTP 400 with a structured provider error object;
   - HTTP 400 with an unstructured or empty body;
   - HTTP 200 with the expected completion envelope;
   - HTTP 200 missing the expected `choices` field;
   - malformed JSON and unexpected tool-call shape.
4. **Assert safe classification.** Each failure must produce a bounded error category and safe structural metadata. Tests must assert that raw payloads, secrets, and untrusted provider text are not leaked. Never synthesize a completion or `choices`, and never treat malformed responses as success.
5. **Run targeted adapter tests and G9.42.** Use the exact candidate commit and preserve the validation receipt, catalog, and hashes.
6. **Only then consider one minimal live request.** It requires explicit manual authorization and must be separately labeled as a compatibility smoke test, not a full provider benchmark. Record exact endpoint/model configuration class, response status, safe envelope shape, and normalized outcome.

## Decision rules

- If the request violates the documented provider contract, correct the configuration or adapter and add a regression fixture.
- If the request conforms but HTTP 400 persists, retain the failure and seek provider-side diagnostics; do not broaden retries first.
- If the response is HTTP 200 but has no expected completion envelope, classify it as a malformed provider response.
- If the response normalizes successfully, rerun only after G9.42 passes, then evaluate evidence quality separately.
- Do not interpret provider compatibility success as evidence of diagnostic correctness.
