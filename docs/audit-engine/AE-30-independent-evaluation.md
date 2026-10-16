# AE-30 — Independent Evaluation of Repository Audit and Controlled Self-Correction

**Validation profile:** G9.32  
**Status:** implementation milestone; acceptance requires the deterministic
AE-30 evaluation, GitHub targeted validation, full regression, and evidence
verification.

## Purpose

AE-30 is an independent evaluation layer for the repository-audit control loop
introduced by AE-29. It does not replace the controller's own tests. Instead,
it composes the public APIs in an evaluator with independently defined
expected outcomes.

The target capability is:

```text
repository snapshot
      ↓
audit finding
      ↓
LLM/neural handoff
      ↓
repair candidate
      ↓
independent verification
      ↓
post-repair audit
      ↓
decision
      ↓
decision memory
      ↓
bounded continuation
```

The evaluation is deliberately repository-maintenance focused. It does not
generate scientific writing or scientific content.

## Evaluation classes

The reference evaluator contains positive, negative, adversarial, isolation,
boundedness, replay, and memory-boundary cases.

Important adversarial cases include:

- stale repair reuse across repository snapshots;
- protected validation/workflow path modification;
- stale neural handoff reuse;
- tampered decision records;
- forged `accept_repair` session transitions.

## Independent expectations

The evaluator does not import or call the AE-29 test helpers. It constructs
its own synthetic repository state, findings, repairs, verification receipts,
and expected decisions using the public API.

This makes the evaluation useful as a second line of defense against a
self-consistent unit-test suite.

## Acceptance metrics

AE-30 requires:

- all reference cases pass;
- unauthorized controller state changes in negative/adversarial cases = 0;
- replay failures = 0;
- decision-memory authorization violations = 0.

The resulting evaluation report is content-addressed and tamper-evident.

## Boundary exposed and corrected

AE-30 identified that `advance_session` was a public state-transition
boundary that trusted a validly digested decision record too much. A caller
could manufacture an `accept_repair` record without the repair/verification/
post-audit chain.

G9.32 therefore adds a second integrity boundary. Before sealing a session,
the transition is revalidated against the complete controller-result artifact
chain.

## What AE-30 does not establish

AE-30 does not qualify:

1. live LLM quality or provider behavior;
2. the production LLM prompt;
3. repository-wide defect discovery;
4. unattended authoritative-checkout mutation;
5. authenticity of an external verifier receipt.

These are recorded as explicit open dependencies rather than silently treated
as solved.

## Production-readiness interpretation

A green G9.32 result means the **defined deterministic control-loop evaluation**
passed. It must not be interpreted as permission to turn on unattended
LLM-driven repository mutation.

Before such automation, the project still needs a trusted verifier-admission
mechanism and a separately controlled live-model qualification procedure.
