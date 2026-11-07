# AE-32C active provider matrix — Cloudflare and OpenRouter only

**Decision date:** 2026-11-07
**Status:** Approved active evaluation scope
**Applies to:** AE-32C manual live evaluation, provider preflight, and round-robin batch assessment

## Decision

The active AE-32C live-evaluation matrix is reduced to two providers, in this order:

1. Cloudflare
2. OpenRouter

NaraRouter is suspended from new live AE-32C requests and is excluded from the active round-robin matrix. This is a suspension of active evaluation, not deletion or rewriting of historical evidence. Existing NaraRouter adapter code and deterministic compatibility tests may remain for historical reproducibility unless a separate change explicitly retires them.

## Basis for suspension

On 2026-11-07, a user-run initialization request to `router.bynara.id` returned HTTP 403 with Cloudflare Error 1010:

- `error_name`: `browser_signature_banned`
- `error_category`: `access_denied`
- `retryable`: `false`
- `owner_action_required`: `true`
- `what_you_should_do`: do not retry; the site owner has blocked the user-agent
- Ray ID: `a56d1ce18ba4f015`

This response is an upstream access-control rejection. It is not a model completion, malformed `choices` envelope, evidence failure, or diagnosis result. The response explicitly says not to retry. No further request should be made to this endpoint unless the provider/site owner resolves the access restriction and a new live test is separately authorized.

This single event does not retroactively explain earlier NaraRouter HTTP 200 or HTTP 400 observations. Those historical records remain as originally recorded.

## Active batch protocol

| Parameter | Active setting |
|---|---|
| Provider order | Cloudflare → OpenRouter |
| Rounds | 4 by default; operator may select 1–4 |
| Trials per round | 2 |
| Canonical four-round batch | 8 provider trials |
| Pause | 120 seconds by default; 30/60 seconds are exploratory deviations |
| Conditions per eligible trial | Independent baseline and graph-assisted conditions |
| Source snapshot | Same exact validated source snapshot for both conditions |
| Validation prerequisite | Successful exact-commit G9.42 validation |
| Dispatch | Manual only, with explicit live-call confirmation |

A four-round batch therefore contains eight provider trials and, where common prerequisites pass, up to sixteen independently recorded condition outcomes. A provider or condition failure must not suppress later eligible conditions or trials. All trial artifacts, including failures, remain part of the denominator and are retained.

## Acceptance semantics are unchanged

The provider reduction does not relax any acceptance criterion. Reports must continue to distinguish:

- transport and API result;
- response-envelope validity;
- baseline completion;
- graph protocol completion;
- required source coverage;
- textual witness support;
- evidence completeness;
- overall trial/batch acceptance; and
- independently reviewed diagnostic correctness.

Textual witnesses are not semantic proof. Protocol completion is not diagnostic correctness. A batch can correctly fail its overall gate while preserving useful per-trial evidence.

## Implementation boundaries

- The batch evaluator's active `PROVIDERS` sequence is `("cloudflare", "openrouter")`.
- The manual round-robin workflow, single-provider live workflow, and provider-preflight workflow offer only Cloudflare and OpenRouter.
- The active workflows do not receive or pass `NARAROUTER_API_KEY`.
- Historical NaraRouter reports, fixtures, and adapter-specific regression tests are preserved; they are not new live evaluations.
- No provider call is introduced on push, pull request, schedule, or other automatic trigger.
- No automatic code edits, commits, or pushes are introduced.

## Required validation before the next live batch

1. Verify current remote `main` and `stage1/section-uuids` HEADs; the supplied snapshots are dated 2026-10-24 and 2026-10-30 respectively and are not proof of current remote state.
2. Review and apply the branch-specific patches without force.
3. Run the updated round-robin workflow contract tests and targeted AE-32C batch tests.
4. Run the complete declared G9.42 profile on the exact development commit.
5. Confirm the manual round-robin workflow validates and checks out that exact commit before reading provider secrets.
6. Only then dispatch the four-round Cloudflare → OpenRouter batch with a successful validation run ID and explicit consent.
7. Reconcile all eight trial records, manifests, checksums, provider subtotals, and aggregate counts.

**No live batch is authorized by this decision record.** It defines the provider scope; live execution still requires the existing manual authorization and exact-commit validation gates.
