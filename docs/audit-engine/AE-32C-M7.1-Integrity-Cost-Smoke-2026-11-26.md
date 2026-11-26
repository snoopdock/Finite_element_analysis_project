# AE-32C M7.1 Native Integrity-Cost Smoke — 2026-11-26

**Workflow run:** [45774182880](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45774182880)  
**Branch:** `stage1/section-uuids`  
**Exact source revision:** `5d6d4089edc5b147f5e94e0364330acf09780113`  
**Run attempt:** 1  
**Result:** all five backend jobs and aggregate summary succeeded.

## 1. What this run establishes

The M7.1 workflow executed the parity-gated native benchmark for NetworkX, SciPy, python-igraph, graph-tool and the SNAP isolated worker. Every backend used:
- 7 fixed E.8.5 adversarial-fixture queries;
- 2 warm-up calls per query;
- 5 measured repetitions per query;
- independent report verification after execution.

The reports record query timing samples, per-query integrity-audit timing samples, engine construction time, native adjacency lookups, native edge-occurrence counts, runner/Python/library environment and result digests. The integrity-audit counter is measured explicitly; it is not inferred from total query latency.

This is a single-fixture smoke characterization. It is not a multi-seed task campaign, memory study, production-sized workload, or cross-backend ranking. Runner and Python environments differ across jobs and must remain separate evidence strata.

## 2. Graph-tool runner compatibility correction

The investigation found a real CI portability defect:
- An earlier graph-tool job on an AMD EPYC 7763 runner terminated with signal 132 (`Illegal instruction`) while using `graph-tool-base` build `_400`.
- A rerun on an Intel Xeon 6975P-C runner completed with the same CPU-specific build.
- The conda-forge graph-tool feedstock assigns build-number offset `+400` when `microarch_level == 4`; x86-64-v4 includes AVX-512 foundation and related instruction-set requirements.
- The AMD EPYC 7763 runner reported AVX2 and no AVX-512 flags. AMD's published architecture material shows Zen 3 does not implement AVX-512, while x86-64-v4 includes AVX-512 feature requirements.

References:
- [conda-forge graph-tool feedstock build recipe](https://github.com/conda-forge/graph-tool-feedstock/blob/main/recipe/meta.yaml)
- [x86-64 psABI microarchitecture levels](https://gitlab.com/x86-psABIs/x86-64-ABI/-/blob/master/x86-64-ABI/low-level-sys-info.tex)
- [AMD EPYC 7763 product information](https://www.amd.com/en/products/processors/server/epyc/7003-series/amd-epyc-7763.html)
- [AMD instruction-set compatibility matrix](https://gpuopen.com/download/GDC2024_AMD_Ryzen_Processor_Software_Optimization.pdf)

The workflow now sets `CONDA_OVERRIDE_ARCHSPEC=x86_64`, disables the graph-tool environment cache so the override is applied during a fresh solve, and asserts that `graph-tool-base` resolves to build `_100`. The successful graph-tool artifact records:
- CPU: AMD EPYC 7763 64-Core Processor;
- Python: 3.12.3;
- graph-tool: 3.9;
- package: `graph-tool-base-3.9-py311hdd21613_100.conda`;
- selected build target: generic x86-64.

The E.8.5/E.8.8 graph-tool job uses the same generic x86-64 build policy and passed in [run 45773593165](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/45773593165). This removes dependence on which GitHub-hosted CPU happens to receive the job. It is an environment-compatibility correction, not a change to graph-tool's semantic traversal implementation.

## 3. Integrity-audit cost observation

The graph-tool report for the fixed 5-node / 8-edge-occurrence E.8.5 fixture recorded, for the `outgoing_all` query:
- median per-integrity-audit time: 299,068 ns;
- median combined integrity-audit time per measured query: 604,117 ns;
- median full query time: 1,350,254 ns;
- engine construction: 1,273,709 ns;
- 5 measured calls, with 2 warm-ups;
- 10 integrity-audit invocations across the 5 measured calls.

These numbers characterize only this fixture, this runner and this generic graph-tool build. They are not a general backend performance estimate and must not be used to rank computational options. The value of the measurement is that it makes the full-projection integrity-audit cost visible separately from the query timing.

## 4. Workflow corrections made

The M7.1 workflow required several corrections before the successful run:
1. Push-event runs now normalize empty `workflow_dispatch` inputs in the shell to `REPEATS=5` and `WARMUP=2`, then pass the resolved values as job outputs.
2. The `GITHUB_OUTPUT` writes are grouped to satisfy actionlint/shellcheck.
3. The graph-tool environment is solved without restoring a stale CPU-specific cache, and its resolved package build is asserted.
4. The package assertion uses `micromamba list --explicit` in the micromamba shell rather than assuming a `conda` executable is present.
5. The graph-tool job now runs the graph-tool benchmark and publishes graph-tool evidence; it no longer contains the copied SNAP worker command or worker-image artifact path.
6. The SNAP isolated-worker job remains separate and continues to record its image identity.

The successful run's actionlint job passed before the five backend jobs.

## 5. Remaining G6 work

This run provides valid initial G6 environment and integrity-cost evidence, but G6 should not be declared fully closed. The benchmark uses a small fixed fixture and does not characterize:
- task-level structural, dependency, path and impact operations at representative workload sizes;
- multiple seeds and graph-shape strata;
- memory/peak-resident-set behavior;
- SNAP startup/IPC/worker lifecycle cost separately from native traversal;
- the cost of projection validation under larger node/edge counts;
- runner-to-runner variance under a controlled environment.

The next useful tranche is a task-level cost campaign that reports each backend independently against the same named task workload, keeps environment strata explicit, and does not compute a winner or aggregate score. G4 also remains Partial; a cost measurement does not prove atomic snapshot semantics.

## 6. Authority and interpretation

The workflow reports explicitly preserve:
- `backend_auto_selection_permitted=false`;
- `performance_winner_established=false`;
- `scientific_approval_permitted=false`;
- `production_approval=false`.

The libraries remain alternative computational options selected only by relevance to a future audit task. M7.1 smoke timing is supporting evidence, not a selection policy or suitability verdict.
