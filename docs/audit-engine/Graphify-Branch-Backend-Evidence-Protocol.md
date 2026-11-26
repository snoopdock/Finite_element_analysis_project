# Graphify evidence protocol for branch-specific graph-backend status

## Purpose

Graphify is an analysis artifact used to inspect code structure independently for each repository branch. The current workflow produces separate snapshots for `main` and `stage1/section-uuids`, each bound to an exact source commit.

The workflow does not calculate cross-branch graph deltas, infer branch equivalence, or rank graph libraries. The graph libraries are alternative computation options; their relevance depends on the audit problem and required operation.

## Evidence boundary

A Graphify node or edge can help locate:

- a backend package import or dependency;
- an adapter class or wrapper;
- construction and registration sites;
- call relationships between audit-engine components and adapter methods;
- tests and fixtures associated with a backend.

These are structural leads, not execution proof. In particular:

- dependency installation is not adapter construction;
- adapter construction is not adapter registration;
- registration is not invocation;
- invocation is not proof that the selected backend performed the requested operation correctly;
- a passing import test is not backend conformance.

Graphify code-only extraction does not establish dynamic dispatch, runtime reachability, successful computation, semantic correctness, or suitability for a particular audit workload.

## Per-backend assessment protocol

For each backend, assess each branch independently and retain the exact branch SHA and Graphify artifact digest.

| Dimension | Required evidence |
|---|---|
| Dependency | Declared package/version and import site |
| Adapter implementation | Concrete adapter methods and supported operation contract |
| Registration | Factory, registry, plugin, or explicit construction path |
| Reachability | Source-followed call path from an audit-engine entry point to the adapter |
| Invocation | Test or controlled run proving the adapter method is called |
| Native computation | Evidence that the underlying library performs the operation, not merely that a wrapper returns a fixture |
| Behavioral conformance | Assertions over outputs, failure modes, and edge cases |
| Structural conformance | Assertions over graph invariants, identity, mutation/snapshot behavior, and resource/side-effect boundaries |
| Problem relevance | Evidence that the operation is appropriate for the specific audit workload |

## Status vocabulary

Use these states per backend, per branch, and per required operation:

- **FUNCTIONAL** — the reachable adapter path is exercised, native computation is demonstrated, and the required behavioral and structural conformance tests pass for the stated operation.
- **PARTIAL** — some operations or layers are demonstrated, but at least one required operation or conformance dimension remains unverified.
- **DORMANT** — a bounded and documented source/call-path investigation establishes that no reachable invocation path exists within the declared audit-engine scope. Mere absence from Graphify output is insufficient.
- **UNVERIFIED** — available evidence does not support one of the other states, including when Graphify coverage or call-path extraction is incomplete.

A status must include its scope. For example, a backend can be functional for neighborhood queries but unverified for strongly connected component analysis. Do not collapse operation-specific evidence into a global library score.

## Branch snapshot interpretation

Each Graphify run records:

- branch name;
- exact source commit SHA;
- Graphify version;
- node and edge counts;
- SHA-256 digest of the graph JSON;
- execution log and structural report.

Compare evidence only after independently assessing each branch snapshot. A later source-level review may explain differences, but this Graphify workflow itself does not perform cross-branch comparison.

## Operational limitations

The workflow uses code-only extraction and cluster-only rendering. It does not run the audit engine, load native backends, invoke adapters, or execute conformance tests. The workflow therefore cannot itself assign FUNCTIONAL or DORMANT status.

Those statuses must be produced by a separate evidence review combining Graphify navigation with source tracing and targeted structural/behavioral tests. Preserve abstention when the evidence boundary is insufficient.
