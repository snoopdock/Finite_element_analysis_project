# ADR-074 — DRAT Deletion Is Proof State, Not Semantic State

## Status
Accepted — G3.4.4.

## Decision
A DRAT `delete` step removes one matching clause occurrence from the proof checker's active formula only. It does not assert that the clause is false, obsolete, disproven, or removed from any canonical semantic model.

The reference checker is intentionally strict: deleting a clause that is not currently present rejects the certificate. Literal ordering is ignored for deletion matching because CNF clause semantics are order-independent, while addition order remains significant because the first literal is the RAT pivot.

## Rationale
Proof compression and checker-state management must not leak into audit semantics or finding lifecycle.
