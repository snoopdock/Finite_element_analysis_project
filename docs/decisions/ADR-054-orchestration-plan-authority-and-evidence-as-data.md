# ADR-054: Orchestration Plan Authority and Evidence-as-Data Boundary

## Status

Accepted for G3.3.0.

## Context

Autonomous auditors consume code, documentation, tool output, evidence and verifier receipts. Some of those inputs may be adversarial or simply malformed. An auditor must not interpret content discovered during analysis as instructions to expand its own authority.

## Decision

The precomputed `OrchestrationPlan` is the sole authority for verifier execution during a G3.3.0 run.

Evidence, graph metadata, source text, verifier details and receipts are treated as data. They cannot:

- add an action to the running plan;
- authorize a new execution mode;
- increase the resource budget;
- trigger a finding directly;
- request persistence into audit memory.

Sandboxed or controlled-external execution modes require explicit permission in the budget before planning.

## Consequences

This creates an auditor-security boundary before external tools, solvers, or generated execution harnesses are introduced. Later orchestration stages may replan, but replanning must create a new versioned plan rather than mutate an executing plan from evidence content.
