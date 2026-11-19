# AE-32C E.8.3.1 — SciPy side-channel parity corrective release

**Status:** Corrective package prepared; fresh GitHub G9.42 validation required  
**Target:** `stage1/section-uuids` only  
**Failed parent:** run `44540515564`, source commit `82eb9c36426985c4246e668f2164c6639b049982`

## Failure evidence

The E.8.3 targeted G9.42 selection passed 539 tests with three optional-native skips. The full regression failed:

- 3,487 passed
- 20 failed
- 22 errors
- 11 skipped
- 3,540 total

The dominant error was `SciPy relation/metadata side-channel parity failure` in the existing G6.1 and G6.2 benchmark suites. E.8.3 had extended SciPy's side-channel records with explicit `relation` and `occurrence` fields, but the legacy verifier still expected the earlier E.8.2 record shape. This rejected valid E.8.3 projections and prevented the G6.2 campaign fixture from being created.

The remaining independent test failure was an exception-contract mismatch: duplicate semantic node identities were rejected during SciPy projection construction with `ValueError`, before the benchmark verifier could raise `BenchmarkError`.

## Corrective decisions

1. Keep the richer E.8.3 SciPy side-channel schema. Do not remove relation labels or occurrence identities.
2. Update the benchmark verifier to require the exact richer schema:
   - relation side-channel: source, target, relation, occurrence;
   - metadata side-channel: source, target, relation, attributes, metadata, occurrence.
3. Read back `SciPyAdapter.iter_native_edges()` and compare by canonical edge occurrence, not CSR iteration order. CSR iteration groups edges by sparse row and is not required to reproduce the original edge-list ordering.
4. Validate the benchmark graph before constructing adapters so the benchmark API raises its documented `BenchmarkError` for duplicate or excessive graph input. The lower-level projection constructor continues to reject malformed canonical identities with `ValueError`.
5. Promote G6.1 and G6.2 benchmark tests into the G9.42 targeted set so this compatibility boundary is checked before full regression.

## Authority and scope

This is a read-only validation correction. It does not alter backend selection, graph traversal semantics, evidence generation, provider calls, repository write authority, or the E.8.4 impact-analysis feature. It does not weaken or skip benchmark tests.

## Validation

Local Python 3.13.5:

- Focused G6.1/G6.2 benchmark tests: 78 passed.
- Updated G9.42 targeted selection: 617 passed, 3 skipped.
- Full local repository regression: interrupted by the execution environment's 60-second limit; no local full-regression pass is claimed.
- Fresh GitHub G9.42 validation is mandatory for acceptance.
