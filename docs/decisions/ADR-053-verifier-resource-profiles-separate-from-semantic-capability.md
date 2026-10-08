# ADR-053: Verifier Resource Profiles Are Separate from Core Verifier Semantics

## Status

Accepted for G3.3.0.

## Decision

Do not add cost, runtime, containment, or orchestration priority fields to `VerifierDescriptor`.

Instead, bind a verifier to a separate `VerifierOrchestrationProfile` containing:

- verifier ID and version;
- method class;
- relative cost units;
- maximum evidence-state capability;
- execution containment mode;
- deterministic/side-effect metadata.

Profiles must version-match active verifier implementations. Unprofiled verifiers receive no implicit cost and are not scheduled by the cost-aware planner.

## Rationale

A verifier descriptor answers what a verifier can semantically verify. A resource profile answers how an orchestration policy may choose to run it. Combining the two would make operational estimates part of semantic authority and would cause routine cost recalibration to alter verifier identity.

`cost_units` are policy-relative units. They are explicitly not wall-clock time, money, confidence, probability, evidence strength, or correctness.
