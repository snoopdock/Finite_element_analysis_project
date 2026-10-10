# Manual semantic validation dispatcher

Install `.github/workflows/00_manual_semantic_validation_dispatcher.yml` on the **default branch (`main`)**. This is the *only* required workflow copy. A workflow-dispatch entry point must exist on the default branch to appear in the GitHub Actions UI. The workflow file executes from the branch chosen in GitHub's **Run workflow** selector; keep that selector set to `main` for the stable dispatcher. The `target_branch` input determines the actual repository code tested.

1. Commit the dispatcher file to `main` (once).
2. Merge/apply the G3.4.6 patch to `stage1/section-uuids`.
3. Open **Actions → Manual Semantic Validation Dispatcher → Run workflow**.
4. Leave **Use workflow from** set to `main`. Set `target_branch` to `stage1/section-uuids`, `milestone` to `G3.4.6-publication`, and `full_regression` to enabled.
5. Download the JUnit XML and `provenance.json` artifact from the workflow run. The run fails if targeted tests or full regression fail.

For G3.4.5 choose `G3.4.5-detached`, which additionally invokes `tools/validate_semantic_detached_proof_artifacts.py`. For new milestones, edit the allowlisted profile choices and case branches in this one dispatcher on `main` or design a trusted, versioned test entry point. Avoid accepting unsanitized input as a shell command.

Security note: selected branches are treated as trusted code because installing their dependencies and executing their tests can run arbitrary commands. The workflow uses read-only repository permissions, does not expose secrets, and does not upload the entire checkout. Protect `main`, restrict manual dispatch permissions as appropriate, and use fixed commit SHAs when reproducibility is critical.

This dispatcher runs tests and scripts *from* the selected branch; it does **not** execute a separate YAML workflow stored only in that branch. Such cross-workflow execution requires a different reusable-workflow arrangement and GitHub's corresponding ref and permissions semantics.
