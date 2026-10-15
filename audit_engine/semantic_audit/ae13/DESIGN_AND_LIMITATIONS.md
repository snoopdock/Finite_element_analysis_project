# AE-13 D1–D3 Combined Design Validation

**Status:** opt-in additive implementation and adversarial pilot, not general Audit Engine readiness or completion of every AE-13 security task.

## D1 — Verified Legacy Compatibility Adapter

The canonical entrypoint remains the modern AE-01 source-bound audit and its existing evidence/rule machinery. `adapt_legacy` is a **separate read-only adapter** that imports the preexisting `ASTExtractor` and `SymbolClassifier`. It does not invoke `runner.run()` (which writes reports into the current directory), modify `runner.py`, or execute analyzed source code.

For each explicitly admitted UTF-8 Python file, the adapter records its exact SHA-256, the original legacy classification, a deterministic occurrence ID, the unresolved semantic details, and a graph projection through the **existing** backend-independent `SemanticGraph`. Graph admission validates unique nodes, endpoints, and occurrence IDs. Replaying with `validate_legacy_report()` rejects altered sources, fabricated classification elevation, or changed occurrence identities. Unparsed sources become incomplete. The source root is read-only; special files and symlinks are rejected or explicitly excluded.

**Crucial:** legacy classifications remain `observed` / `not_verified`. `findings` is empty. Import module text is not converted into a proven dependency; call spelling is not a resolved callee. The old `from . import x` limitation is preserved as visible uncertainty rather than issuing an empty graph node. This adapter does not assert parity with AE-01 or replace its policy findings.

## D2 — Many-to-many evidence associations and verification

The G3 `GraphAnalysisResult`, `SemanticObservation.evidence_ids`, `EvidenceRecord`, `VerificationObligation`, `VerificationService`, `VerificationReceipt`, and `ObservationContractVerifier` remain authoritative existing components. The D2 gate **does not replace their schemas**. It derives explicit identity-bearing `(analysis, observation, evidence)` associations, requiring that each direct edge evidence reference match the *exact* observation tuple and regenerate the G3 edge hash from the original provenance. Thus mere co-membership of IDs in an analysis no longer suffices.

Plans contain multiple observations with **all** their declared witness IDs, and an explicit `all`/`any` aggregation policy. One observation may appear in multiple plans. Several observations may appear in one plan. The pilot evaluates each selected graph triple through the existing G3 observation-contract verifier and then aggregates the result. It checks the selected registered verifier's exact type and descriptor, the G3 receipt's selected evidence, receipt content identity, source analysis ID, graph fingerprint and semantic context. A source graph may be independently admitted and bound; using it changes the outcome label from `declared_graph_contract` to `attested_graph_contract`.

**Assurance boundary:** this does not check arbitrary logical predicates, real Python path feasibility, or semantic correctness of the source graph. It is a bounded, explicit graph-fact contract gate. Human review and other independent verification methods are still required for stronger claims. Future generalized verifiers must declare operator semantics and validate their own evidence consumption. The evidence/receipt bindings here are a **prototype policy** for later incorporation into existing protected production interfaces, not an assertion that all G3 consumers have been migrated.

## D3 — Cost and invalidation experiments

The controlled benchmark builds synthetic source IDs, source observations, shared evidence IDs, association links and verification-plan references. It reports canonical JSON byte sizes under normalized-versus-duplicated representations, plus independent scan and indexed-query timing samples. Invalidation is defined by source → observations → shared evidence → all dependent observations → plans, so a source change can invalidate plans associated with a different file. The indexed result is compared against an independent full-scan result on every run.

This is **not** a disk-storage benchmark, resident-memory (RSS) measurement, persistent-database benchmark, GitHub runner measurement, or production latency guarantee. Compression, database indexes, network costs, encryption and concurrency are not modeled. The package bounds workloads, disallows invented cross-revision equivalence, and preserves all raw timings.

## Security and authority

No source execution, GitHub writes, push triggers, automated fix publication, untrusted verifier plugins or arbitrary shell commands. Input files are admitted as bounded regular files; the release checker scans **all** ZIP entries, including directory entries, and rejects special files, traversal paths, checksum mismatches, unsafe ratios, and missing test targets.

## Further work before full AE-13 acceptance

1. Integrate the reviewed binding policy into authorized existing verification and finding entrypoints with comprehensive backwards-compatible G3 tests.
2. Establish source-to-program-fact accuracy beyond legacy syntax and AE-01's current bounded source model; do not claim interprocedural certainty.
3. Build empirical D3 persistence benchmarks with realistic source revisions, memory/RSS profiling, database indexes, concurrency and data lifecycle/reclamation.
4. Evaluate compatibility with protected AE-01 publication and legacy consumers before replacing any entrypoint.
5. Resolve additional previously reproduced memory, file-admission, and execution-isolation risks via separate gates rather than claiming that this package has solved them all.
