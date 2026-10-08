# Candidate-to-Canonical Knowledge Lifecycle

Candidate knowledge is intentionally non-authoritative. It may originate from a
future LLM, GNN, heuristic, extraction system or human suggestion.

The G3.1.1 lifecycle is:

```
Candidate relation
      |
Explicit verification obligation
      |
Confirmed verification receipt
      |
Promotion policy
      |
Canonical semantic edge
```

Promotion records the candidate id, policy id/version, verification receipt,
verifier, source analysis, semantic-context fingerprint and evidence ids.
Endpoint identities must already exist. Promotion does not silently invent
entities, bypass verification, or treat model confidence as semantic truth.
