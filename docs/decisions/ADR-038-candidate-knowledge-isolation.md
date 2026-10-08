
# ADR-038: Candidate Knowledge Isolation

## Status
Accepted for G3.1.0.

## Context
Future LLM, embedding, or graph-neural components may propose relations, specifications, or suspicious patterns. Treating such output as canonical graph content would allow probabilistic inference to redefine semantic authority.

## Decision
Learned or heuristic output SHALL first be represented as `CandidateKnowledge` in state `proposed`.

Candidate artifacts SHALL NOT expose a canonical graph mutation API. Promotion into the canonical semantic graph is deferred until a domain-specific promotion contract can require validated evidence and explicit semantic projection policy.

## Consequences
Neural assistance can later be introduced without weakening the authority of deterministic semantic contracts. Candidate hypotheses remain inspectable, attributable, rejectable, and independently verifiable.
