# ADR-028 --- Semantic Projection Boundary

## Status

Accepted

## Context

The repository distinguishes between observed facts and interpreted
meaning.

Automatically converting observations into conclusions creates hidden
reasoning steps and allows semantic errors.

## Decision

All transitions from observation to interpretation SHALL occur through
an explicit projection or evaluation boundary.

## Required Flow

    Observation

    ↓

    Evaluation / Projection

    ↓

    Semantic Relationship

    ↓

    Conclusion or Finding

## Examples

Forbidden:

    Citation -> Supports -> Claim

Required:

    Citation Occurrence

    ↓

    Evaluation

    ↓

    Support Relationship

    ↓

    Claim

## Rationale

Detection is not interpretation.

Compilation is not scientific correctness.

Citation existence is not evidence validity.

## Consequences

Reasoning becomes traceable and auditable.
