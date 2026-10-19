# AE-32C Patch 2 — Semantic Graph Fidelity and Workflow Evidence

## Purpose

This patch follows AE-32C Patch 1 (G9.42) and improves the source relationships consumed by the future interactive investigation engine. It is a stage-branch patch for `stage1/section-uuids`; it does not modify the central validation dispatcher.

## Changes

### AE-32A source model

- Recognizes alphanumeric Audit Engine package names such as `ae32a`, `ae32b`, and `ae32c`.
- Detects explicit Python source roots declared in `pyproject.toml` or `setup.cfg` without executing packaging code.
- Uses configured roots when mapping Python paths to module names and resolving relative imports.
- Includes uppercase `.PY` files in Python parsing and module inventory.
- Records import execution context when statically identifiable: `module_level`, `type_checking_only`, `function_local`, `class_body`, or `conditional_module_level`.
- Parses GitHub Actions workflow YAML structure, reads trigger declarations in scalar, sequence, and mapping forms, and inspects `run` steps instead of searching arbitrary workflow text for Python-looking substrings.
- Reports unresolved or invalid active workflow declarations as audit issues rather than assuming they were analyzed successfully.
- Uses a consistent physical source-line convention that does not split on Unicode line separators inside Python string literals.

### AE-32B evidence graph

- Adds occurrence-level symbol identities that include source path, source hash, qualified name, line, and symbol kind while preserving a legacy `symbol_id` for compatibility.
- Makes ambiguous legacy symbol selectors fail explicitly when multiple occurrences exist.
- Reports collisions where multiple physical files map to the same logical module.
- Normalizes a statically observed script workflow invocation to its module identity when the mapping is unambiguous, while retaining the direct file edge.
- Restricts workflow-context discovery to active workflow candidates and imposes bounded traversal visits.
- Uses identifier-boundary checks for lexical related-test fallback so module prefixes do not count as exact references.
- Excludes `TYPE_CHECKING`-only imports from runtime-oriented workflow paths and reports import context on individual path steps.
- Corrects exact-limit truncation semantics for repository search, symbol search, and decision-history search.
- Adds traversal-node and traversal-step budgets to graph-neighbor and graph-path queries, plus workflow-candidate and path-visit budgets. Resource-limited queries expose partial coverage and a stop reason instead of implying exhaustive coverage.
- Builds adjacency indexes once per graph walk rather than scanning the full edge list for every visited node.
- Increments the graph projection contract version to `ae32b/source-evidence-projection/v2`.

## Evidence semantics and limitations

All workflow invocation and import relationships remain static observations. Parsing a workflow command does not prove that the workflow ran, and following an import edge does not prove that the import was reached at runtime. Shell parsing is intentionally conservative; dynamic expressions, complex wrappers, unresolved working directories, and commands whose target cannot be resolved must not be represented as confirmed invocation edges.

Source-root detection only uses supported, explicit static configuration. Dynamic `setup.py` logic is not executed. If package roots cannot be determined, the source model retains its repository-relative naming convention rather than guessing.

Traversal budgets apply to graph analysis queries exposed by AE-32B. They do not turn the entire repository scanner into a runtime sandbox or establish correctness of the underlying software.

## Tests added

`tests/semantic_audit/test_ae32c_patch2_graph_workflow_fidelity.py` covers alphanumeric component names, workflow trigger forms, comment/echo false positives, configured source roots and relative imports, import contexts, uppercase `.PY`, module/symbol collisions, exact related-test matching, source line fidelity, transitive workflow context, truncation boundaries, and traversal budgets.

The profile also targets the existing AE-32A/AE-32B suites and graph traversal/dependency/path tests.

## Validation status

No local repository runtime or test suite was executed while preparing this patch. The tests are authored but unexecuted. Apply Patch 1 first, then this patch, and run the consolidated G9.42 validation manually through the established GitHub Actions process. GitHub acceptance remains pending until the user supplies the resulting logs and evidence bundle.
