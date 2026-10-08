
# ADR-040: Semantic Context Versioning

## Status
Accepted for G3.1.0.

## Context
A content fingerprint over nodes and edges identifies a graph snapshot but not necessarily its meaning. Identical graph structure can be interpreted differently when graph schema, relation vocabulary, projection rules, or analysis contracts change.

## Decision
Every G3 analysis result SHALL expose a versioned `SemanticContext` with:

- graph schema version;
- relationship-vocabulary version;
- optional projection-contract version;
- analysis-contract version.

The semantic context has its own deterministic fingerprint. Analysis identity and downstream verification are bound to this fingerprint.

## Consequences
Changes in vocabulary or projection semantics invalidate downstream verification even when node/edge bytes are unchanged. This makes semantic drift visible to later G3.2 snapshot and long-term-memory machinery.
