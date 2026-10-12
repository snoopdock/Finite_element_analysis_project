# G6.1 — Reproducible graph backend benchmarking and parity gate

## Scope

Use the *existing* `NetworkXAdapter` (attributed directed multigraph) and `SciPyAdapter` (CSR directed adjacency plus relation and metadata side channels) to produce an auditable performance comparison. The canonical `SemanticGraph` is unchanged.

## Experimental design

- Deterministic seeded directed synthetic graphs: a cycle backbone, extra random edges, some parallel edge occurrences, and self-loops. The workload fingerprint binds to the exact canonical node/edge payload.
- `smoke` synthetic cases: 16 nodes/55 edges and 64 nodes/260 edges; `standard`: 64/260, 256/1024, 768/3072. An optional fourth case uses the **actual, independently verified** GE-02 persisted graph.
- Separate measurements: **adapter projection** from source graph and **directed reachability query batch** against an already-built adapter. Query batches use three predeclared source nodes. No projection time is charged to queries, and no graph generation or verification time is charged to either metric.
- Each measured metric is warmed up twice, then timed 7 times by default using `perf_counter_ns`. Raw observations, median, p95, minimum, and maximum are all reported; no fixed time threshold is used as a pass criterion.
- The parity gate independently checks identity maps, directed multiedge multiplicity, NetworkX entity/edge data preservation, the SciPy CSR shape and numerical multiplicity, side-channel identity/relation/metadata, and directed reachability sets against the source graph.
- A source and environment manifest includes Python, OS, NetworkX, SciPy, NumPy versions, processor architecture, CPU count, scenario fingerprints, GE-02 head and generation (if included), and a digest of the report. During detached verification, synthetic graph fixtures are regenerated and the persisted graph is revalidated against the repository. Hashes detect accidental/naive modification, not authenticated provenance.

## Interpretation and limitations

1. The two adapters are **not semantically equivalent in representation**: NetworkX preserves attributed typed multiedges, while SciPy's CSR matrix alone loses relation and metadata structure (stored in separate side channels). The benchmark only compares **shared directed connectivity queries** and projection costs.
2. Comparing runs on different CPUs, VMs, OSes, installed versions or loads is not a controlled comparison. Reported medians/p95 are descriptive for the captured execution only. Benchmarks never select a backend automatically; later policy changes would require separate explicit review.
3. CSR `data + indices + indptr` bytes are reported as **SciPy matrix storage**, not total process memory or a cross-backend RAM comparison.
4. Tests require structural parity; they do not assert that a library is universally faster, that the graph is scientifically correct, or that any model/claim is approved.
5. Graph snapshots and source repository files are **read-only**; only detached workflow artifacts are written. GitHub Actions is invoked by **workflow_dispatch** only. No push triggers or automatic branch mutations.

## Validation

Run `G6.1` via the existing **Manual Validation Dispatcher** (`stage1/section-uuids`, regression=`profile`), then `G6.1 Manual Graph Backend Benchmark and Parity Review` on `main` with `standard`, `repeats=7`, `include_persisted=true` (default). Download the generated report, execution/verification receipt, and JUnit artifact. Use the full GitHub regression and parity checks as G6.1 acceptance criteria. More dataset classes and benchmark reproducibility between runners can be evaluated during G6 milestone closure.
