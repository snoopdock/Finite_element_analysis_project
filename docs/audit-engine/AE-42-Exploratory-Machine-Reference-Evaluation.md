# AE-42 — Exploratory machine-reference evaluation

**Branch:** `stage1/section-uuids`  
**Baseline roadmap:** `docs/audit-engine/AE-42-Project-Roadmap-and-Status-Baseline.md`  
**Scope:** AE-32D exploratory evaluation only  
**Status:** implementation committed; GitHub Actions acceptance pending.

## 1. Objective

Continue AE-32D software evaluation without waiting for independent reviewers, while preserving the distinction between fixture-derived machine references and benchmark gold labels.

AE-42 introduces a provisional machine-reference track. It does not adjudicate cases, freeze the pilot, alter case ground truth, grant primary eligibility, or claim that any A/B/C condition has achieved a measured result.

## 2. Provisional reference inventory

The registry contains exactly the six cases in the AE-32D manifest:

| Case | Provisional reference | Basis |
|---|---|---|
| Provider interface | defect | Pinned consumer/adapter mismatch and runtime failure reproduction |
| Branch unbound | defect | False-branch unbound local reproduced |
| No-defect control | no_defect | Initialization and both branch paths satisfy fixture contract |
| Ambiguous provider | ambiguous | Provider implementation absent; runtime conclusion unsupported |
| Exception suppression | defect | Declared OSError propagation contract violated at runtime |
| Stale data flow | defect | Stale return value observed (105 vs expected 95) |

Every entry is linked to the exact case source commit and its AE-41 machine-verification ledger run/artifact. The reference kind is `machine_derived_fixture_contract`. The registry is explicitly prohibited from writing gold labels or granting primary eligibility.

## 3. Trial contract

A trial record is bound to:
- a known manifest case;
- one of `A_deterministic`, `B_graph`, or `C_graph_llm`;
- the exact source commit recorded by the machine-reference registry;
- a non-empty configuration digest;
- a unique trial ID and case/condition pair.

Outcomes are `defect`, `no_defect`, `abstain`, or `error`. Failed trials must have outcome `error` and a failure reason. Missing trials are not synthesized into the input; the scorer explicitly emits them as missing for every absent case/condition pair. Duplicate trials and source mismatches are rejected.

This is a trial-record contract, not a claim that provider calls or full A/B/C campaigns have already been run.

## 4. Exploratory metrics

For each condition, the scorer emits:
- raw counts of provisional defect, no-defect and ambiguous references;
- true positives and false negatives/unresolved defect cases;
- false positives;
- explicit no-defect predictions;
- appropriate abstention on the ambiguous case;
- explicit abstentions, errors and missing trials;
- exploratory defect-detection rate, false-positive rate, abstention rate and ambiguous-case abstention rate;
- per-case outcomes and trial IDs.

Missing and failed trials remain in the report and are not silently removed. The denominators are the six-case provisional inventory, with defect and no-defect rates using their respective reference subsets.

The report always states:
- `status=exploratory_only_not_gold_adjudication`;
- `gold_adjudication_performed=false`;
- `primary_benchmark_score=false`;
- `primary_benchmark_eligible_cases=0`.

These metrics are not primary benchmark scores and must not be represented as independent accuracy estimates.

## 5. Implementation

- `evaluation/ae32d/machine-reference-registry.json`
- `evaluation/ae32d/machine-reference-registry.schema.json`
- `evaluation/ae32d/exploratory-trials.schema.json`
- `tools/ae32d_exploratory_evaluation.py`
- `tests/semantic_audit/test_ae32d_exploratory_evaluation.py`
- Updated `.github/workflows/ae32d-machine-verification.yml`
- Updated `evaluation/ae32d/README.md`

The validator cross-checks registry case IDs and source commits against the manifest, case records and AE-41 ledger. It fails if case ground truth is no longer pending, if review is unexpectedly marked adjudicated, or if primary eligibility is true. The scorer is read-only with respect to benchmark records.

## 6. Acceptance requirements

1. Registry schema validates and contains exactly the manifest case set.
2. Every reference source commit, workflow run and artifact matches the AE-41 ledger.
3. All case ground-truth labels remain pending and all primary-eligibility flags remain false.
4. A/B/C trials must use unique case/condition pairs and the pinned source commit.
5. Unknown cases, duplicate trials, invalid outcomes and source mismatches fail closed.
6. Missing, failed and abstaining outcomes remain visible in denominators and case-level records.
7. Exploratory reports cannot be labeled as gold adjudication or primary benchmark scores.
8. Unit tests include valid scoring, missing-trial accounting, duplicate rejection and source-mismatch rejection.

## 7. Status and next steps

The implementation is committed. The workflow must pass before AE-42 can be marked validated. The next work is AE-43 exploratory integration only after the scorer and registry pass the acceptance workflow. AE-43 should use retained or explicitly generated A/B/C trial outputs and must not fabricate provider/model results.

AE-43–AE-46 remain proposed sequencing from the consolidated roadmap, not pre-approved commitments. Before assigning later milestone numbers, reconcile the repository's existing roadmap records.

## 8. Non-goals and preserved backlog

AE-42 does not close:
- independent gold adjudication, scoring-rubric approval or pilot freeze;
- task-specific graph-backend suitability;
- Note 002 activation, coherent snapshot, delta, incremental equivalence, cache and publication implementation;
- M7.5 persistent package storage or a universal consumer gate;
- provider/model qualification beyond the recorded AE-31/32C scope;
- remediation decision/patch transaction implementation;
- formal solver portfolio acceptance;
- frozen-kernel self-examination and enforceable termination;
- Future Supervisor scientific/documentary validation.

These remain visible in the consolidated roadmap and are not displaced by AE-42.
