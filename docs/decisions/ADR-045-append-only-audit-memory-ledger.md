# ADR-045: Append-Only Audit Memory Ledger

## Status

Accepted.

## Decision

Durable audit memory is an append-only ledger of serialized, snapshot-bound artifacts. Loading audit memory never changes canonical semantic state and never promotes candidate knowledge.

## Consequences

- historical findings and receipts remain inspectable;
- audit knowledge can be versioned and diffed;
- identity collisions with different content are rejected;
- persistence is separated from semantic authority.
