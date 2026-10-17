# AE-32A — Architecture and Wiring Audit

## Objective

Produce a reproducible, read-only account of which Audit Engine capabilities are present in source, have test references, are imported by other production modules, are invoked by GitHub workflows, make live model-provider requests, use graph-analysis APIs, expose model tool-call loops, or emit measurable evaluation evidence.

AE-32A is an inventory and wiring audit, not an LLM auditor. It does not import or execute inspected project code, call providers, apply repairs, or make claims about scientific content.

## Run

```bash
python -m audit_engine.semantic_audit.ae32a \
  --repo-root . \
  --output-dir artifacts/audit_engine/ae32a
```

The command writes four artifacts:

- `architecture_wiring_report.json` — evidence-bound report, file manifest, component matrix, import edges, workflow commands, and findings.
- `architecture_wiring_report.md` — human-readable summary and capability matrix.
- `execution_dependency_map.mmd` — Mermaid map of observed production imports and workflow commands.
- `execution_dependency_map.json` — machine-readable edges and the same Mermaid representation.

The output directory must be inside the audited repository and must not be a symlink. The output directory is excluded from the next scan so rerunning the command does not make its own output part of the input manifest. Files are published by atomic replacement. The optional source and runner revisions must be hexadecimal Git commit IDs; the scanner never infers them.

The manual-only GitHub workflow `AE-32A Architecture and Wiring Audit (Report Only)` is supplied under `MAIN_BRANCH/`. After G9.40 is accepted, promote the `MAIN_BRANCH/` payload to `main` and run that workflow from `main`, selecting `stage1/section-uuids` as the target branch. It checks out the target branch as data and runs the scanner from the trusted workflow commit. It has read-only repository permissions, no secrets, and no push/commit step.

## Status semantics

- **Implemented:** source files exist and were included in the scan.
- **Test presence:** a test file references the component. This is not a test-pass result.
- **Production consumer:** another non-test/non-documentation Python module imports the component.
- **Workflow invoked:** a scanned workflow command explicitly invokes the module or script.
- **LLM transport:** a source file contains both a recognized model endpoint indicator and a provider HTTP call.
- **Exposed as LLM tool:** a detectable tool-call/dispatch indicator exists. This is heuristic and is not inferred from ordinary HTTP requests.
- **Graph API:** direct source indicators for the repository's semantic graph analysis API are present.
- **Measured:** operational counters or evaluation-harness fields are present. The report distinguishes operational telemetry from live-model quality measurement.

Static absence is reported as “not observed,” not proof that dynamic behavior is impossible. Parse failures and source-scope exclusions make the overall scan incomplete. No live execution, network request, provider call, or repository mutation is performed.

## Design constraints

- Use deterministic path ordering and SHA-256 source manifest entries.
- Do not follow symlinks or allow output paths to escape the repository root.
- Keep evidence as repository-relative path/line references rather than copying source text into the report.
- Separate observed facts from interpretation and include limitations for findings.
- Do not change the FEA writing/convergence behavior or enable automatic self-correction.

## Current expected purpose

This stage should establish the actual wiring baseline before AE-32B exposes graph-grounded evidence tools and AE-32C introduces an interactive LLM tool-use loop. It should make clear which existing components can be reused and which integrations remain unproven.
