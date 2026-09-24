
# ADR — L1-L23-L Migration Strategy

## Status

Accepted

## Context

The repository contains existing functionality.

A rewrite would create unnecessary risk.

---

# Decision

Use incremental migration based on contracts.

---

# Rules

1. Preserve working behavior.
2. Introduce boundaries first.
3. Refactor only when ownership is unclear.
4. Add tests with every migration.

---

# Result

The repository evolves toward L1-L23-L without losing existing capabilities.
