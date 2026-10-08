# Audit Memory Query and Re-verification Lifecycle

## Historical Memory Is Not Authority

The audit-memory ledger stores immutable historical artifacts. G3.2.1 adds queries over this ledger while preserving the rule:

> Stored previously does not mean valid now.

A memory record can be retrieved because it references an evidence identity or rule, but current validity must come from graph evolution and re-verification state.

## Query Dimensions

The initial query contract supports:

- artifact type;
- artifact ID;
- snapshot ID;
- evidence ID;
- verification receipt ID;
- rule ID.

Filters combine deterministically, and queries cannot mutate memory or the canonical graph.

## Re-verification Lifecycle

```text
Historical artifact
      ↓
Current graph transition
      ↓
Impact propagation
      ↓
CURRENT / RECHECK_REQUIRED / STALE
      ↓
Versioned re-verification plan
      ↓
Future execution layer
```

The execution layer is deliberately deferred. This keeps memory lookup, validity assessment, planning, verification, and rule judgment as distinct responsibilities.
