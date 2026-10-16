# AE-28 / G9.30 — Neural/LLM Semantic Interpretation Boundary

## Status

Implementation prepared; a G9.30 corrective revision is pending the manual
GitHub validation profile. The prior run had one failure caused by an
incorrect test expectation: an unexpected field inside `model` was correctly
rejected as model metadata, but the test expected an outer-envelope error.

## Position in the Audit Engine

```text
AE-24  source-bound semantic contracts
  ↓
AE-25  symbolic invariant reasoning
  ↓
AE-26  semantic identity/evolution
  ↓
AE-27  controlled neurosymbolic proposal gateway
  ↓
AE-28  neural/LLM interpretation intake
```

AE-28 is the first milestone that can consume an actual neural/LLM result as
an Audit Engine input. It does not invoke a provider itself.

## Operating contract

The external model adapter is responsible for producing:

1. bounded raw output bytes;
2. a normalized canonical JSON response.

AE-28 binds both to a source/semantic request and converts the response into
the AE-27 candidate-only proposal format.

The model is not authoritative.

## Error-domain separation

AE-28 validates three distinct response domains:

```text
response envelope
      ↓
model trace
      ↓
model metadata
      ↓
AE-27 proposal semantics
```

Failures are classified at the domain where they occur. In particular,
unexpected fields such as `confidence` inside `model` are rejected as
`Invalid model metadata`; they are not treated as an outer-envelope failure.

## Repository audit use

The future LLM can inspect bounded repository context and propose:

- semantic relationships;
- possible violated constraints;
- candidate dependency/ownership interpretations;
- possible mismatch hypotheses;
- candidate repair targets.

AE-28 does not decide whether any of those claims are true.

## Self-correction boundary

AE-28 does not modify the repository and does not write durable decisions.
AE-29 will introduce a bounded investigation/repair cycle with explicit
decision records and guarded writeback.

## Prompt boundary

The exact runtime LLM prompt is deliberately deferred until AE-30. AE-28
records only a task/prompt digest and input manifest so that the eventual
prompting system can be bound to an auditable request without embedding a
premature prompt design in the semantic core.
