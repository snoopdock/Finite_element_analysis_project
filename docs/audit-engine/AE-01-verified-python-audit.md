# AE-01 — Verified Python Source Model and Architecture Audit

**Contract:** `ae01/v1`; **scope:** bounded, repository-local Python source static analysis and a single explicit architecture rule. This is not a claim of full Python runtime semantics or generalized repository correctness. The legacy `audit_engine.semantic_audit.runner` remains unchanged.

## Reused repository infrastructure

AE-01 retains `SemanticGraph`/`SemanticNode`/`SemanticEdge`, G3 `SemanticGraphAnalysisService`, `GraphQuery`, `DomainRuleLoader`, `DomainRuleExecutor`, `GraphAttributeConstraintVerifier`, `VerificationService`, sealed `VerificationReceipt` and `FindingFactory`. No duplicate architecture rule interpreter or proof system is introduced.

### Analysis stages and boundaries

1. **Exact source manifest.** Scan `*.py` below the explicit root, excluding exact directory names rather than substring matches. Record repository-relative paths, SHA-256 on **raw bytes**, deterministic order, encoding, parse errors, excluded paths and counts. Do not follow file/directory symlinks. Source changes during read/after scan become failures/inconclusive results; no incomplete scan is clean. Sources without edges remain represented.
2. **AST source facts.** Capture an occurrence ID, precise line/column/end-span, `ImportFrom.level`, aliased names, package context, TYPE_CHECKING/conditional context, dynamic imports and call-site receiver spelling. Static import resolution only relates names to inventoried modules; explicit `internal`, `external`, `ambiguous`, `unresolved` classifications accompany occurrence facts. `candidate` calls are **not** claimed as definite callees. Full dispatch, monkey-patching, run-time import hooks and symbol-flow inference are out of scope.
3. **Complete semantic graph.** Canonical `SemanticGraph` contains `Module`, `SourceFile`, `ImportOccurrence`, `Function`, `CallSite`, `ExternalModule`, `IMPORTS`, `HAS_IMPORT`, `HAS_CALL`, `DEFINED_IN`, and `DEFINES` facts. Parallel imports carry independent occurrence IDs and source digests. Source code bytes remain authoritative, not a dependency fingerprint alone.
4. **Verified architecture-policy graph.** A reproducible projection preserves **all internal module import edges** and only `Module` nodes. Each module is further projected into an independently fingerprinted one-hop graph for G3 execution. The published complete graph, global policy graph and source-specific projection fingerprints are **different by design**, all linked through the same sealed generation. This bounded projection makes the 40k-node complete source graph practical to audit without expensive repetitive global graph traversal.
5. **Rule and verified findings.** AE-01 currently supports only `architecture.no_production_to_experimental_dependency`. `production`, `experimental`, `stable`, `deprecated` labels must be supplied explicitly by a reviewer-controlled JSON object mapping exact module names to lifecycle. Unknown internal dependency classification, absent required applicability, unresolved imports, conditional dependencies and scan failures make assurance **inconclusive**; zero findings alone is never grounds for compliance. An executed rule produces G3 obligations, validation receipts, and findings bound to source-hashed edges. Confirmed defects are policy-relative and static, not a proof that a code path executes at runtime.
6. **Publication and independent checking.** All JSON output is canonical UTF-8; a generation is assembled under a staging directory, hashes are sealed, the directory is made visible, then an atomically updated `LATEST.json` marks only the latest completed attempt. `LATEST.json` becomes `running` at attempt entry, `failed` on exception, and is never accidentally an old successful run after a failed attempt. The `--verify` operation independently checks file membership, byte hashes, manifest/graph/projection fingerprints, receipt-to-edge bindings, finding witness consistency and verdict completeness. Supplying `--source-root` and `--policy` additionally checks live source and policy against sealed evidence.

## CLI — run safely

```bash
python -m audit_engine.semantic_audit.ae01 \
  --source-root tests/ae01/fixtures/forbidden \
  --output-root /tmp/ae01-controlled-forbidden \
  --policy specs/rules/architecture/no_production_to_experimental_dependency.yaml \
  --lifecycle tests/ae01/fixtures/forbidden/lifecycle.json
python -m audit_engine.semantic_audit.ae01 \
  --output-root /tmp/ae01-controlled-forbidden --verify \
  --source-root tests/ae01/fixtures/forbidden \
  --policy specs/rules/architecture/no_production_to_experimental_dependency.yaml
python scripts/ae01_fixture_demo.py
```

Exit codes: **0** complete, applicable and no verified violation; **2** complete with at least one verified policy violation; **3** inconclusive/incomplete (may still contain source-verified findings); **4** execution/publication failure. Exit 2 is an expected **positive control** in the prohibited fixture, not a software test failure.

Output: `LATEST.json`; `generations/<run_id>/manifest.json`, `source_facts.json`, `graph.json`, `policy_graph.json`, `policy.json`, `rule_executions.json`, `report.json`, `SEAL.json`. Never manually modify the sealed generation. `LATEST` must be completed to verify; an old generation remains available historically, but does not constitute the latest successful status after a failed attempt.

### Demonstrable correctness and limits

- The positive control requires one correctly located real forbidden dependency and a confirmed/validated G3 receipt.
- The negative control requires an actual verified *refutation* of the same rule and **non-zero applicable observations** (not merely an empty graph).
- Repeated import occurrences retain independent edge/evidence/receipt identity; a source edit alters the source digest and run identity, including edits without import changes.
- Source parse problems, ambiguous imports, missing lifecycle classifications, conditional dependencies and empty policy target scopes produce an explicit incomplete/unassessed verdict.
- Output and source symlink paths are forbidden or explicitly excluded. Only exact directory exclusions are accepted. Very unusual adversarial filesystem races, inaccessible parent directories, hostile local OS processes, or an attacker who can rewrite *all* hashes and seals are not cryptographically defended against. `SEAL.json` is an integrity hash tree, **not a digital signature**, and a complete authentication trust chain has not been established.
- Results are deterministic under identical input bytes, configuration, parser version and analysis environment. No sound Python interprocedural call graph, dynamic `sys.path` proof, symbolic execution, scientific correctness proof or cross-repository import/environment inference is claimed.
- The source byte-digest binds scanned Python source; it does not by itself attest a Git commit/branch or the execution environment. Separate repository and CI evidence should be retained for acceptance.

## Testing and GitHub validation

`python -m pytest -q tests/ae01 tests/semantic_domain_verification tests/semantic_verification` and `python -m pytest -q tests/` are local gates. `python scripts/ae01_fixture_demo.py` exercises both labeled end-to-end outcomes including an independent artifact check. The initial `G9.1` profile is a **compatibility transport name** because `validation/schema.json` currently requires `G<number>.<number>` IDs. The implementation milestone is *AE-01*. The authoritative **main-branch dispatcher has not been uploaded**; compatibility on GitHub must be verified by manually triggering the existing dispatcher, entering `G9.1` if accepted, and uploading the resulting logs. This patch does **not** change the `main` workflow or create any automatically triggered workflow.

## Follow-up exclusions

No autocommit/autopush, auto-remediation, autonomously applied suggestions, arbitrary Python call-graph certainty, runtime crash forensics, mutation-coverage scoring, scientific extraction auditing, or document-writing quality judgments are implemented here. Those are separate milestones requiring scope-specific evidence and tests.
