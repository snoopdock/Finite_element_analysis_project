# G6.2 — Multi-seed graph-backend benchmark acceptance

**Roadmap:** This is the original **G6 — Graph Backend Benchmarking**, following the completed G5 OWL work. GE (operational graph engine) and G4 (RDF) are not renamed. The next original milestone after G6 acceptance is **G7 — Semantic Reasoning Rules**.

## Motivation

G6.1 established basic reproducible deterministic workload generation, source/projection integrity and parity between two existing adapters: `NetworkXAdapter` (attributed directed multigraph) and `SciPyAdapter` (sparse connectivity projection with separate metadata and relation side channels). Its timing measurements were one-run observations, not a scientifically established backend winner. G6.2 adds a bounded repeated-seed campaign without modifying these existing adapters or allowing automatic selection.

## Protocol and interpretation

- Choose 2–7 **distinct, ascending deterministic seeds**. The standard manual workflow uses `20261013,20261014,20261015`.
- For every seed, run the existing G6.1 `make_report` and independent `verify_report`. Record 3 standard seeded synthetic workload sizes and optionally the exact verified persisted GE graph (the *same* persisted version throughout the campaign).
- Per graph/operation/backend, take the median of within-run medians, median absolute deviation (MAD), and min/max across seeds. Raw observations and complete G6.1 subreports remain embedded for independent replay.
- Report *paired descriptive* NetworkX/SciPy median ratios only where denominators are positive. A null ratio means the denominator is zero; no invented values.
- For standard or smoke workloads, compare the first and last synthetic scale descriptively. This is *not* Big-O complexity estimation; the datasets are not controlled to isolate every factor.
- G6.1's algorithm order is fixed rather than randomized; concurrent runner load, CPU and caching can bias wall times. Distinct seeds change the graph topology, not the physical run environment. Measurements across seeds are **not independent samples of a hardware population**. A confidence interval, significance claim, universal faster-backend statement or automatic selection would be inappropriate.
- A SHA-256 report fingerprint proves the report has not changed since hashing; it is **not cryptographic proof of genuine timing observations**. The verifier checks mathematical consistency of samples and reconstructs synthetic graph structure/parity, but it cannot independently rerun past wall-time measurements. Evidence must be interpreted with this boundary.
- The SciPy sparse matrix **does not itself preserve all semantic information**. Graph identity, edge multiplicity, and metadata side-channel parity remain strict functional acceptance gates. Memory bytes are only for SciPy CSR and do not represent full adapter process footprint.
- No scientific truth, formal OWL consistency, semantic entailment, graph write, or backend-selection authority is granted.

## G6 acceptance criteria

1. G6.1 verified functional parity and provenance remains green across NetworkX and SciPy for deterministic synthetic and persisted datasets.
2. G6.2 manually runs a multi-seed campaign, re-verifies every embedded G6.1 report, and independently recomputes summary and scaling descriptors.
3. Rehashed forged parity, changed sources, altered aggregates, mixed runner environments, mixed persisted graph versions, unauthorized selections and malformed inputs are rejected.
4. Full `Manual Validation Dispatcher` regression succeeds with profile `G6.2`, and dedicated manual campaign workflow succeeds.
5. The report explicitly disclaims a universal performance winner and preserves both raw observations and environment metadata. If these conditions pass, the original G6 benchmarking *infrastructure* can close. Further real-hardware benchmarks are an operational investigation, not a reason to delay G7 indefinitely.

## CLI usage (at root of development branch)

```bash
python -m audit_engine.semantic_audit.graph.backend.backend_benchmark_campaign run \
  --profile standard --seeds 20261013,20261014,20261015 \
  --repeats 5 --warmup 2 --include-persisted --repository . \
  --report g6-2-campaign.json
python -m audit_engine.semantic_audit.graph.backend.backend_benchmark_campaign verify \
  --repository . --report g6-2-campaign.json
```

The workflow on `main` executes these commands after checking out `stage1/section-uuids` into `source/`, running targeted tests and installing dependencies. `contents: read` permission, `workflow_dispatch` trigger only, no git push and no graph write. The artifact contains the reports and JUnit results. Do not compare numeric medians across different runner architectures, installed dependency versions, or CI load without explicit controls.
