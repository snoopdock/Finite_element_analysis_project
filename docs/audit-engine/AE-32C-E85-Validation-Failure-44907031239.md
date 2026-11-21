# AE-32C E.8.5/E.8.8 Run 44907031239 — Wrong-branch dispatch analysis

**Run:** [44907031239](https://github.com/snoopdock/Finite_element_analysis_project/actions/runs/44907031239)  
**Event:** `workflow_dispatch`  
**Actual workflow ref:** `main`  
**Actual workflow/source SHA:** `c54919c39bf656ef4562320008f6aa7df8b2e844`  
**Conclusion:** this run did not execute the Stage1 source or the SNAP worker correction. Its failures are branch-content/workflow-controller mismatches, not evidence of defects in the current Stage1 adapters.

## 1. Evidence

The run metadata identifies `head_branch=main` and `head_sha=c54919c39bf656ef4562320008f6aa7df8b2e844`. Job logs independently confirm checkout of `origin/main` at that SHA.

| Job | Failure | Cause |
|---|---|---|
| SNAP | `3.9.19` not found on Ubuntu 26.04 | Old main workflow still pinned the obsolete exact interpreter and used `ubuntu-latest`; Stage1's Ubuntu 24.04 / CPython 3.9 correction was not in the executed workflow revision |
| NetworkX | `tests/semantic_graph/test_m1_adapter_protocol_networkx.py` not found | The main source tree did not contain the Stage1-specific test file |
| SciPy | `tools/gb03_native_backend_conformance.py` not found | The main source tree did not contain the Stage1 conformance runner |
| igraph | Same missing conformance runner | Same branch mismatch |
| graph-tool | `.github/environments/e85-graph-tool.yml` not found | The main source tree did not contain the Stage1 conda environment definition |
| Summary | Failed | Correctly propagated the failed jobs |

The graph-tool post-job cleanup also logged a missing micromamba shell directory after environment provisioning failed. This is secondary cleanup noise, not an independent adapter defect.

## 2. Root cause and distinction

GitHub `workflow_dispatch` runs the workflow revision on the selected ref. The run selected `main`, so both the workflow YAML and the default checkout resolved to main. The Actions log proves this explicitly.

GitHub documents that the workflow file must exist on the default branch for manual dispatch to be enabled, and the UI normally exposes a branch selector. GitHub also supports specifying a target ref using `gh workflow run ... --ref BRANCH` or the REST dispatch request's `ref` field. See:
- [GitHub Docs — Manually running a workflow](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow)
- [GitHub Docs — Events that trigger workflows](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)

The user's inability to select Stage1 in the mobile UI is not resolved by this run's metadata; the run only proves that main was selected. To avoid dependence on that UI selector, the main-branch workflow controller has been changed to expose an explicit `source_ref` choice input, defaulting to `stage1/section-uuids`, and all job checkouts use that input. The workflow definition on main is synchronized from the corrected Stage1 workflow, so the SNAP runner fix and all required environment/test files are used together.

## 3. Technical review of the dispatch correction

This design separates two refs that GitHub otherwise couples in the UI:
- **Workflow controller ref:** `main`, which supplies the workflow definition and allows the default-branch manual trigger.
- **Tested source ref:** `inputs.source_ref`, explicitly passed to `actions/checkout` in each job.

The workflow records the checked-out commit SHA in job summaries, preventing the GitHub run's `head_sha` (the controller commit) from being mistaken for the tested Stage1 source SHA. Concurrency is keyed by the selected source ref to avoid cancelling or serializing unrelated target-branch runs.

This is a valid manual-dispatch pattern: GitHub's workflow-dispatch payload distinguishes the dispatch ref from workflow inputs, and `actions/checkout` accepts a specific branch/ref. The choice input is constrained to the intended Stage1 branch. It avoids changing the repository default branch, avoids merging Stage1 implementation into main, and avoids copying implementation code into main beyond the workflow controller file.

## 4. Corrective action and validation boundary

The main workflow controller file is updated to:
1. use the corrected Stage1 workflow definition;
2. offer `source_ref=stage1/section-uuids`;
3. explicitly checkout that source ref in each backend job;
4. record the actual checked-out SHA;
5. retain the isolated SNAP Ubuntu 24.04 / CPython 3.9 binary-wheel procedure and diagnostic artifact.

No adapter source code was changed in response to this wrong-branch run. The dispatcher change must be exercised in a new manual run. Acceptance requires the run logs to show `Selected source ref: stage1/section-uuids`, the checked-out SHA to match the then-current Stage1 head, and all expected files to be present. Only then should the SNAP installation/smoke result be interpreted.

**Status:** run 44907031239 is excluded from Stage1 conformance evidence. The dispatch-controller correction is committed separately on main; the analysis record is committed on Stage1.
