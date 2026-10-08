# Semantic Audit Rules Architecture

## Rule principle

Rules are policy artifacts. Verifiers are evidence-testing mechanisms.

A rule declares:

- its domain and stable identity;
- the verification obligation type;
- the verifier that must be used;
- which analysis targets are eligible;
- verifier parameters;
- the decision and evidence state that trigger policy;
- severity and finding language.

The verifier does not decide severity. The rule does not perform graph
algorithms. The finding factory does not re-verify evidence.

## Why this separation matters

It makes policy diffable, testable and reviewable while preserving explicit
provenance from observation to finding. It also allows multiple rules to reuse
a verified semantic mechanism without embedding policy in implementation code.
