# AE-32C Patch 3 — Interactive LLM Investigator

## Purpose

Patch 3 adds a provider-neutral, read-only investigation loop that connects existing provider adapters to AE-32B's nine repository evidence tools. It does not replace the semantic graph or existing provider factory.

## Public API

```python
from audit_engine.semantic_audit.ae32c import (
    InvestigationLimits,
    RepositoryInvestigator,
)
from providers.factory import build_provider

budget = {
    "max_llm_calls_per_run": 6,
    "max_tokens_per_call": 800,
}
provider = build_provider(
    {"budget": budget},
    budget,
    "openrouter",
    "deepseek/deepseek-v4.1-flash-1017",
)
investigator = RepositoryInvestigator(
    ".",
    provider,
    limits=InvestigationLimits(
        max_rounds=6,
        max_tool_calls=10,
        max_tokens_per_call=800,
        max_total_tokens=18000,
    ),
)
report = investigator.run("Investigate the failed validation run")
```

The example requires the selected provider's configured environment secret. Do not run it in ordinary regression tests. The `report` object is strict-JSON-compatible and may be rendered as Markdown or published to an existing directory outside the inspected repository.

## Model action schema

Each provider response must contain exactly one JSON object:

- `tool_call`: one registered AE-32B tool name, an arguments object conforming to that tool's schema, and a bounded reason.
- `final`: a diagnosis object containing summary, root-cause assessment, claims, proposed corrective action, limitations and next steps.

Duplicate JSON keys and non-standard JSON constants are rejected. Model output is not executed. The system does not accept native tool calling implicitly; the current common adapter interface is textual.

## Citation verification

Every root-cause assessment and claim must reference evidence IDs from successful tool responses. A root-cause assessment must cite at least one successful evidence item beyond the initial summary. Each source reference must resolve to the actual path, physical line and source SHA-256 in its referenced tool response and match the indexed hash where available. Invalid final diagnoses can receive one bounded repair turn; repeated invalid citations stop the investigation.

The report's assurance label is `references_resolved_not_independently_proven`. Referential integrity is necessary but does not establish that the model's interpretation is causally correct.

## Resource and transport limits

The investigator enforces model-round, tool-call, estimated-token, cumulative-prompt, output-character, evidence-byte, source-snapshot verification and elapsed-time limits. Optional cost limits require a conservative caller-supplied cost estimator. Provider adapters stream response bodies, cap bytes before JSON parsing, cap decoded text, and omit raw HTTP error bodies. The synchronous provider API still limits how strictly a deadline can interrupt a request in progress.

## Security boundary

Repository contents are untrusted evidence. All tool responses are sanitized and detached before entering the ledger. Provider errors are normalized. Report files are permitted only outside the inspected repository. No target code, shell command, patch, commit or push is executed.

## Acceptance status

Patch 3 adds deterministic fake-provider tests and mocked provider-response tests. Those tests have not been executed during patch preparation. A real multi-round live-provider investigation and historical-incident evaluation remain pending Patch 4 and GitHub validation.
