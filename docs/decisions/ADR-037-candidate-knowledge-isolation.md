# ADR-037: Candidate Knowledge Isolation

## Decision

Candidate inferred knowledge cannot directly modify canonical semantic
knowledge.

## Flow

    Candidate
     |
    Verification
     |
    Canonical

## Rationale

Supports future LLM and GNN assistance without contaminating
authoritative knowledge.
