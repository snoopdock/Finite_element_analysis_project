# AE-02.1 — Evidence-bound incremental impact and re-verification planning

**Status:** implementation; GitHub manual validation pending. The code does not execute repairs, edits, tests or policy decisions automatically.

## Purpose and scientific claim boundary

Compare two **separately verified** AE-01 source audit generations and produce a **conservative, bounded reviewer task list**. An import graph is a static observation, not an unrestricted Python call graph. The plan identifies *potentially* affected import dependents, not a proven runtime change, software defect, exhaustive reachability result, or remediation.

The method is purposefully stronger than a graph-fingerprint-only comparison: arbitrary source-byte changes can invalidate a source witness even if the imports are unchanged. Both historical and current import edges are considered, because a removed edge may invalidate prior evidence.

## Pipeline

1. AE-02 independently loads each AE-01 generation using source manifests, generation seals, source witnesses, policy graph and verified finding contract.
2. The prior/current policy graphs are converted into the pre-existing G3 `SemanticGraph` and compared via `GraphSnapshot` and `GraphDelta` (unchanged existing engine). G3 `changes_from_delta` produces deterministic structural change atoms.
3. The existing AE-02 `compare_snapshots` locates added, removed, modified source files and import occurrences, policy identity and finding differences.
4. The AE-02.1 impact adapter constructs a reverse dependency union from both verified generations and propagates review tasks through importer -> imported relationships. BFS records shortest observed chain length and evidence occurrence IDs.
5. The adapter adds source-only edits, changed import bindings, changed lifecycle classifications, graph semantic context, old/new coverage, and explicit budget/completeness state. No mandatory scope is silently exempted.
6. Each emitted witness is linked to its **specific generation ID, artifact seal hash, source file, exact source-file SHA-256, import line/column and observed target**. Identical occurrence IDs in different generations are explicitly distinguished.
7. The comparison record includes a content-derived `plan_sha256` and `comparison_sha256`. A read-only detached CLI verification mode regenerates the output from the two sealed generations and byte-compares canonical JSON.

## Outcomes, and their meaning

| `impact_plan.completeness` | Interpretation |
|---|---|
| `no_detected_change` | No relevant observed source/policy differences under the compared evidence; **not** proof of program correctness |
| `incremental_review_required` | Deterministic potential-impact tasks within the specified budget, with no identified scan/policy completeness blocker |
| `full_review_required` | One or more policy/assurance/scan blockers or an exhausted propagation/output budget prevent incremental sufficiency |

`impact_plan.truncated = true` always adds `budget_exhausted` and fails closed. Incomplete past/current AE-01 assurance or changed policy maps force a full-scope review. A schema omission or dynamic import may still limit confidence beyond the static model: AE-02.1 never asserts Python dependency completeness.

### Algorithmic bounds

Let `V` be the number of observed internal modules and `E` be internal import occurrences in both generations. Reverse-edge construction and unbounded BFS have approximately `O(V + E)` cost. Deterministic sorting adds log factors. Building the G3 delta remains subject to the existing graph snapshot implementation. `max_depth` (default 32) and `max_tasks` (default 2500) guard review-plan size; exhaustion generates `full_review_required`, never a partial "verified clean" conclusion. This is an algorithmic estimate, not a measured performance guarantee.

## Read-only use

```bash
python -m audit_engine.semantic_audit.ae02 \
  --before-output /path/to/old-ae01 \
  --after-output /path/to/new-ae01 > comparison.json

python -m audit_engine.semantic_audit.ae02 \
  --before-output /path/to/old-ae01 \
  --after-output /path/to/new-ae01 \
  --verify-record comparison.json
```

A named historical generation may be selected with `--before-generation ae01-...` / `--after-generation ae01-...`, enabling comparisons after a later unsuccessful attempt. The verifier only reads generation artifacts and comparison JSON.

Exit status: `0` for successfully generated/verified comparison with complete latest AE-01 assurance and nontruncated impact plan; `3` for correct comparison with incomplete latest assurance or truncated impact plan; `4` for invalid/tampered evidence, invalid arguments, or verification failures.

## Explicit limitations

- Static imports do not provide complete dynamic dispatch, arbitrary `sys.path` mutation, entry-point plugin discovery, monkeypatch, `exec`, reflection, imports inside arbitrary runtime-generated code or implicit packaging side effects.
- A dependency chain is *possible impact* and does not prove test failure. Likewise an absent edge cannot prove no runtime influence.
- Policy changed -> full review by design; a label remapping is not an independently verified repair.
- Removed findings are handled by AE-02's prior `reconcile_findings` contracts; they are not automatically marked resolved.
- The source/seal SHA-256 witness is an **integrity commitment** to supplied artifacts. Without externally trusted signatures/attestation it cannot independently prove original authorship or trustworthy publication provenance.
- This implementation is **not** a general incremental execution engine. It **plans** re-verification; execution remains manual. G3 invalidation/re-verification services remain intact.

## Acceptance oracles and independent checks

The `tests/semantic_audit/test_ae021_impact.py` suite uses real AE-01 extraction, rules, G3 graph delta, and sealed evidence. Tests cover positive/negative comparisons, import-chain propagation, deletion, cycles, nested relative imports, conditional imports, unchanged graph/changed source, policy mutation, partial assurance, budgets, manifest provenance, tampering, repeatability, CLI verification, and read-only behavior. Release tests independently assert that profile omission, target-path drift, ZIP tampering, checksum mismatch, traversal paths and compiled files fail.

Run `G9.3` in the **existing main-branch manual dispatcher** targeting `stage1/section-uuids`; `regression_mode=profile`. No automatic triggers or main dispatcher changes are included. Review uploaded detached evidence and record remote acceptance separately from local tests.
