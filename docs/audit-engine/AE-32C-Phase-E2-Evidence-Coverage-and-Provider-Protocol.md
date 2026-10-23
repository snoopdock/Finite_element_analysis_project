# AE-32C Phase E.2 — Evidence Completeness and Provider-Protocol Reliability

## Scientific motivation

The nine prior E.1 live trials passed the exact-commit prerequisite but achieved five of nine operational smoke gates. OpenRouter completed three of three, yet its source reads could be truncated while a diagnosis still made a confident inference. Completion and source-reference resolution are not proof of cause. Phase E.2 establishes a caller-declared, source-bound *inspection-coverage contract*, not an automated semantic truth oracle.

## Coverage contract

`RepositoryInvestigator(required_source_paths=(...))` is optional (default empty). Every declared path must be normalized, repository-relative, indexed and unique; unknown, traversal and overly broad policies are rejected before provider calls. The caller specifies which implementation files must be directly inspected for its bounded purpose. This avoids hardcoding provider-interface semantics into the generic investigator.

Only successful `read_source_file` results with the correct source hash, actual numbered source lines, and a full observed line range satisfy `complete_read_paths`. A `search_repository` snippet, graph relationship, or synthetic source-reference tuple cannot substitute for a direct read. An EOF-overshooting requested end line may legitimately be clamped without making the observed content partial. A read limited to part of a source file does not satisfy full inspection. Large sources may therefore require a different bounded investigation policy; the system reports this limitation instead of claiming completeness.

The accepted diagnosis's `root_cause.source_references` must also bind each required path to a matching **complete** read evidence ID. When the root-cause confidence is `high` and these criteria are not met, the diagnosis is rejected with `high_confidence_required_source_coverage_incomplete`; bounded state-machine recovery proceeds normally. A lower-confidence diagnosis with the gap may be retained for human review, but only as `completed_with_incomplete_evidence` with `diagnosis_submitted_with_required_source_coverage_gap` and a distinct `diagnosis_assurance` value. Neither result counts as a full, verified causal conclusion.

The finalization prompt explicitly reports inspection completeness from the authoritative evidence ledger. Source-reference candidates preferentially expose direct reads instead of exhausting the bounded candidate list on lexical-search citations. Feedback contains paths and bounded structured status, not the raw rejected model output.

For the controlled `ae32c_provider_interface_incident` live fixture, Phase E.2 declares `pipeline/extractor.py` and `providers/adapter.py`. No new read or experiment is performed by the engine automatically: tools remain model-requested, read-only and bounded. An arbitrary other fixture does not inherit the incident-specific policy.

## Provider protocol boundary

OpenAI-compatible adapters now reject responses explicitly marked `length`/`max_tokens` or `content_filter`/`safety`. These are `completion_truncated` and `completion_filtered` provider errors, rather than silently passing a cut-off fragment to the strict JSON parser. Missing finish reason retains the prior conservative behavior. HTTP 200 envelopes without `choices` remain fail-closed. Truncated text, raw responses, and upstream error bodies are not written to diagnostic error messages.

## Evaluation and limits

The comparison summary and Markdown report expose required inspection status, missing complete source reads and missing direct root-cause citations separately from resolved citation count and live completion. The tool is not an independent causal verifier, does not execute the historical incident, and does not prove that a cited line entails a model claim. An external oracle and reviewer are still required to assess diagnostic correctness.

## Acceptance and safety

Run G9.42 with manual dispatcher on `main`, target `stage1/section-uuids`. Targeted and full regression, detached evidence, catalog verification and exact source pinning must all pass. Only then run the manually dispatched, prereq-gated live evaluations. No new workflow triggers, autonomous edits, commits, pushes, or network calls inside the offline profile.
