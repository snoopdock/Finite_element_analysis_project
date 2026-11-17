# E.7-R.3N.7.5.2 — Cloudflare HTTP 429 bounded retry

## Triggering evidence

- G9.42 validation run: `44102378774` — passed.
- Validated Stage1 commit: `baccc16ec07c86b4add5a93a839fa42b366c712a`.
- Live evaluation: `44102881117` — failed.
- Baseline and graph-assisted requests both received HTTP 429 in approximately 0.09 seconds.
- The live workflow explicitly set `FEA_LLM_RETRY_ATTEMPTS=1`.
- The provider logged “waiting 30s” even when no retry was configured or executed. The old log message therefore overstated the action taken.

## Corrective behavior

- Keep `FEA_LLM_RETRY_ATTEMPTS=1` for general pre-response transport behavior.
- Add a separate `FEA_LLM_RATE_LIMIT_RETRY_ATTEMPTS` setting, default 1 and hard-capped at 2.
- Retry HTTP 429 only before any response body or stream is consumed.
- Respect `Retry-After` seconds or HTTP-date values.
- Clamp wait to `FEA_LLM_RATE_LIMIT_RETRY_MAX_WAIT_SECONDS` (default 60 seconds).
- If no valid Retry-After is supplied, use bounded exponential fallback (30 seconds for first retry).
- Close the rejected response before sleeping.
- Do not retry explicit capacity/quota exhaustion.
- Never replay a request after streaming has begun or partial content/tool-call data has been received.
- Report actual HTTP attempt count and rate-limit retry count.
- Report retry exhaustion accurately; do not claim a wait or retry that did not occur.

## Workflow policy

The `main` branch live-evaluation workflow explicitly enables one Cloudflare-only HTTP 429 retry. OpenRouter remains at zero rate-limit retries through this new setting. The existing generic retry count remains one.

## Acceptance

- One 429 followed by success: exactly two HTTP attempts and one retry.
- Repeated 429: one retry maximum, then explicit failure.
- `Retry-After` is honored but bounded.
- Quota/capacity 429 is not retried.
- No retries after a stream starts.
- G9.42, full regression, evidence digest and provenance verification must pass before the next live evaluation.
