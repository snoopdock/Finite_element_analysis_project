# ADR-041: Domain Rule and Verifier Separation

## Status

Accepted for G3.1.1.

## Decision

Domain audit policy is represented as declarative rule data. Verification
mechanisms remain executable components registered behind the verifier
interface.

A domain rule may select analysis targets and name a verifier, but it may not
perform graph traversal, silently upgrade evidence, or create a finding before
verification and rule evaluation complete.

## Rationale

This preserves the G3 boundary:

```
Observation -> Obligation -> Verifier -> Receipt -> Rule Evaluation -> Finding
```

It also keeps policy versionable and reviewable independently from verifier
implementation.

## Consequences

- YAML rules can evolve without embedding policy across Python conditionals.
- Verifiers can be tested independently of severity and finding language.
- One verifier may support multiple rules when the semantic verification
  mechanism is identical.
- Rule execution remains reproducible because verifier id, rule version,
  receipt, graph fingerprint, and semantic-context fingerprint remain explicit.
