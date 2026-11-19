# ADR-047 — Preserve E.8.3 SciPy semantic side-channel compatibility

- **Status:** Accepted for E.8.3.1 corrective implementation
- **Date:** 2026-11-19

## Context

E.8.3 enriched the SciPy adapter's side-channel schema with an exact relationship label and canonical edge-occurrence identifier. The G6.1/G6.2 benchmark verifier still compared the older E.8.2 record shape, omitting those fields. The benchmark suite consequently rejected valid SciPy projections before it could test reachability, benchmark metrics, persistence, report integrity or campaign verification.

The SciPy CSR matrix stores directed connectivity and parallel-edge multiplicity. Exact semantic relation labels, attributes, metadata and edge-occurrence identities remain in canonical side channels. CSR row iteration order differs from the canonical input edge-list order.

## Decision

1. Keep the E.8.3 side-channel schema and its explicit occurrence IDs.
2. Make the benchmark verifier validate the exact schema and all canonical payload fields.
3. Verify native read-back by occurrence identity rather than incidental CSR iteration order.
4. Keep strict multiplicity, relation, attribute, metadata and reachability checks.
5. Normalize malformed benchmark input at the benchmark API boundary to `BenchmarkError`, while retaining lower-level projection validation errors.
6. Include G6.1 and G6.2 benchmark suites in the G9.42 targeted tests.

## Consequences

- Existing scientific benchmark and campaign functionality remains compatible with the E.8.3 SciPy adapter.
- A side-channel mutation, missing/duplicate occurrence, metadata forgery or CSR multiplicity mismatch still fails closed.
- No benchmark tests are removed, weakened or excluded.
- No automatic backend winner or backend-selection authority is introduced.
- The graph remains a read-only structural analysis surface.
