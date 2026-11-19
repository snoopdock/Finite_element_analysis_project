# Branch Graphify Analysis

This tool builds two independent Graphify architecture maps and a Git lineage comparison for:

- main
- stage1/section-uuids

It is read-only with respect to branch history. It does not merge, rebase, reset, cherry-pick, or move either branch. It creates temporary detached Git worktrees, analyzes each snapshot, and removes the worktrees afterward.

## Outputs

The committed report is written to branch-graphify-results/latest/:

- main/graph.html — interactive Graphify map for main.
- main/graph.json — machine-readable graph for main.
- main/GRAPH_REPORT.md — Graphify structural report for main.
- stage1-section-uuids/ — the same three artifacts for the comparison branch.
- git-lineage.json — exact branch SHAs, merge base, ahead/behind counts, and changed-file inventories.
- git-lineage.mmd — Mermaid summary of the branch split.
- architecture-delta.json — node and relationship overlap/differences between the two Graphify snapshots.
- architecture-comparison.md — readable comparison of code-structure changes.
- analysis-report.md — entry point with provenance and links to the artifacts.

Graphify is used for source-code structure extraction. The Git comparison is separate because a source-code knowledge graph is not a Git commit DAG and cannot, by itself, establish branch ancestry.

## Run locally (Windows / PowerShell)

Requirements: Git with worktree support, Python 3.11+, and the Graphify CLI package graphifyy.

From the repository root:

    py -3.11 -m venv .venv-branch-graphify
    .venv-branch-graphify\Scripts\python -m pip install --upgrade pip
    .venv-branch-graphify\Scripts\python -m pip install -r tools\branch-graphify\requirements.txt
    git fetch origin --prune
    .venv-branch-graphify\Scripts\python tools\branch-graphify\run_analysis.py --repo . --base main --compare stage1/section-uuids

The default output directory is branch-graphify-results/latest. Open either branch's graph.html in a browser. The Graphify JSON can also be queried using the Graphify CLI, for example:

    graphify query "How does the LaTeX document model connect to the builder?" --graph branch-graphify-results/latest/main/graph.json
    graphify path "CitationOccurrence" "latex_builder.py" --graph branch-graphify-results/latest/main/graph.json
    graphify explain "EquationOccurrence" --graph branch-graphify-results/latest/main/graph.json

## GitHub Actions

The workflow at .github/workflows/branch-graphify-analysis.yml runs on pushes to main (except result-only commits), manual dispatch, and a weekly schedule. It installs Graphify, analyzes the fetched branch refs, and commits refreshed results to main. Code-only extraction does not require a Graphify API key.

If GitHub Actions is not permitted to push to the repository, enable repository Actions settings that allow workflows to write repository contents, or run the script locally and commit the output yourself.

## Interpretation and limitations

- A Graphify edge describes a code-level relationship extracted from a branch snapshot. It is not proof of Git ancestry, runtime behavior, or semantic equivalence.
- The node/edge delta compares the identities Graphify emits for each snapshot. Treat additions/removals as structural signals to inspect, not as a substitute for reviewing source diffs.
- The Git report is authoritative for merge base, commit counts, commit SHAs, and changed paths.
- This workflow uses Graphify code-only mode to avoid sending repository source to an external LLM and to avoid semantic extraction costs. Community labels may be generic.
- Generated graphs are snapshots. Re-run after meaningful code changes to refresh them.
- Graphify is pinned to version 0.9.112 in requirements.txt so the AST extraction and graph comparison use a known CLI release.

## Safety

The workflow only reads the two branch snapshots. It writes analysis files under branch-graphify-results/latest/ on main. It does not change either source branch or its commit history.
