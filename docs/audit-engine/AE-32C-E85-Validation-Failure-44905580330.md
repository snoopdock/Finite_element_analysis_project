# AE-32C E.8.5/E.8.8 Run 44905580330 — Failure Review and Corrective Action

**Branch:** `stage1/section-uuids`  
**Exact tested source SHA:** `9adc99b9511d0281b18be76d60865dcf13bb16b0`  
**Workflow:** `AE-32C Native Graph Backend Conformance (E.8.5 / E.8.8)`  
**Run:** [44905580330](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/44905580330)  
**Disposition:** graph-tool E.8.5/E.8.8 passed; SNAP worker provisioning failed before package installation or smoke execution.

## 1. Executive findings

The workflow checked out the requested Stage1 branch and exact SHA. NetworkX, SciPy, igraph and graph-tool jobs completed successfully. The overall workflow failed because the isolated SNAP compatibility job requested CPython 3.9.19 on the Ubuntu 26.04 hosted runner, where `actions/setup-python` could not find that interpreter build.

The failure is an environment provisioning incompatibility, not a SNAP API failure and not an adapter conformance failure. SNAP was not installed and the smoke script was not executed. The missing SNAP artifact is therefore expected from the failed setup sequence.

## 2. Job evidence

| Job | Result | Evidence / boundary |
|---|---|---|
| NetworkX | Passed | M1 protocol tests, synthetic E.8.5 and repository-backed E.8.8 report passed |
| SciPy | Passed | Synthetic E.8.5 passed; repository routing gate explicitly deferred |
| igraph | Passed | Synthetic E.8.5 passed; repository routing gate explicitly deferred |
| graph-tool | Passed | 4 graph-tool adapter tests passed; synthetic E.8.5 and repository-backed E.8.8 both passed |
| SNAP | Failed before smoke | Python 3.9.19 unavailable on Ubuntu 26.04; install and TNEANet smoke steps skipped |
| Summary | Failed | Correctly propagated SNAP job failure |

### graph-tool evidence

The dedicated environment installed `graph-tool-base 3.9` with CPython 3.11.18. The adapter test command reported **4 passed, 20 deselected**. Synthetic conformance reported `status=passed`, 34 native adjacency lookups and 96 native edge occurrences read. Repository-backed conformance reported `status=passed`, 45 native adjacency lookups and 86 native edge occurrences read. The three repository context operations reported `graph_tool_vertex_edge_iterators`, zero failed adjacency queries, and positive native lookup/occurrence-read telemetry.

The matching G9.42 run [44904263386](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/44904263386) passed against the same exact Stage1 SHA. Its evidence record reports 53 validation-engine tests passed; 684 targeted tests passed with 5 skipped; and 3,615 regression tests passed with 13 skipped. Evidence integrity, immutable bundle publication/verification and provenance catalog verification passed. Thus the exact-source dual-workflow acceptance gate for the tested graph-tool implementation is met.

This acceptance is scoped to graph-tool-base 3.9 in the tested conda-forge / CPython 3.11.18 environment. It is not a performance claim or blanket production approval; the runtime registry's `production_approval` remains false.

## 3. SNAP root cause

The SNAP job ran on `ubuntu-latest`, which resolved to Ubuntu 26.04. It requested exact CPython `3.9.19`. The setup action failed with:

```text
The version '3.9.19' with architecture 'x64' was not found for Ubuntu 26.04.
```

No package installation occurred. The `snap-stanford==6.0.0` wheel is published for CPython 3.9 on Linux x86-64, so CPython 3.9 remains the correct ABI target for this compatibility probe. The job must use an OS image for which setup-python can provision that interpreter.

## 4. Technical review of the correction

The SNAP probe is intentionally an isolated worker compatibility check: it imports SNAP only, constructs a TNEANet directed multigraph, checks outgoing adjacency, verifies parallel-edge preservation and checks explicit edge-to-semantic-occurrence attributes. It does not import AE-32C code and must not be conflated with adapter acceptance.

The correction therefore:
1. Pins this job to `ubuntu-24.04`, an image on which setup-python provides CPython 3.9 builds.
2. Requests the `3.9` minor line rather than an obsolete exact patch pin; the selected interpreter remains CPython 3.9 and matches the published `cp39` wheel ABI.
3. Installs only the pinned `snap-stanford==6.0.0` binary wheel using `--only-binary=:all:`, preventing an unplanned source build.
4. Keeps SNAP in a separate GitHub Actions job and does not install it into the Python 3.11 project or graph-tool environments.
5. Records setup, installation and smoke-step outcomes even when a prior step fails, and uploads the evidence directory so provisioning failures are diagnosable.

This is preferable to upgrading SNAP's interpreter target without evidence, building the C++/SWIG package during every run, or allowing the SNAP dependency to contaminate the main runtime. The older Ubuntu runner is deliberately scoped to this one legacy binary compatibility job.

## 5. Acceptance boundary and next validation

The workflow correction is not itself proof that SNAP installs or that the TNEANet smoke passes. Re-run the dedicated workflow on the resulting Stage1 head. Acceptance of the SNAP compatibility probe requires:
- CPython 3.9 setup succeeds on Ubuntu 24.04;
- the pinned binary wheel installs without source compilation;
- the smoke report says `status=passed`;
- the report confirms two nodes, two parallel edge occurrences, duplicate outgoing neighbors and distinct semantic occurrence attributes;
- the artifact includes both the JSON report and worker step outcomes.

Even after this smoke passes, SNAP remains `not_implemented` for AE-32C native adjacency until a restricted worker protocol, exact occurrence mapping, repository-level parity, failure handling and provenance contract are implemented and validated. This workflow does not promote SNAP to adapter acceptance.
