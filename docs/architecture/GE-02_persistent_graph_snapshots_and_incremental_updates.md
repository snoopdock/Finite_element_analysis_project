# GE-02 — Persistent Graph Snapshots and Incremental Dependency Updates

## Goal and boundaries

GE-02 is an implementation detour under **GE (Graph Engine)**, not the original
**G4 — RDF Export** roadmap stage. It reuses GE-01's independently projected
`GraphDomainView` and the existing `SemanticGraphEvolutionService` for structural
changes, rather than introducing a separate graph backend or graph-delta model.

### Contracts

- Input: GE-01 `GraphDomainView` derived from scientific graph JSON (or, by API,
  a source-verified G3.5 assurance cycle). User-authored JSON is not trusted as
  scientific truth.
- Storage: `.graph-state/scientific/HEAD.json`, immutable content-addressed
  `objects/`, `commits/`, and `transitions/` directories.
- `HEAD.json` changes atomically after the associated objects have been synced.
- Every read verifies the reachable commit chain, exact file hashes, graph
  fingerprints, canonical serialization, and graph-delta reproduction.
- Writers use an exclusive lock and optimistic expected-HEAD compare-and-swap.
  A stale lock (e.g. from a killed runner) is **not** silently deleted.
- Repeated identical inputs are idempotent; changed graphs create incrementally
  linked commits and deterministic review-candidate reports.
- Dependency propagation is a bounded **review-only** reverse traversal for
  known structural relations. It is **not** semantic entailment, causal
  inference, scientific verification, human approval, or authorization to edit.
- `SCIENTIFIC_RELATION` edges do not imply directional dependencies.
- SHA-256 supports tamper detection, not cryptographic provenance or signer
  authentication. A malicious actor capable of replacing the entire store and
  its root of trust can forge a self-consistent history.

## GitHub-only operation

1. Apply `MAIN_BRANCH/.github/workflows/ge02_manual_graph_snapshot.yml` on
   `main` and the remaining files under `STAGE1_SECTION_UUIDS/` on the
   development branch.
2. **Validation:** manually run the existing `Manual Validation Dispatcher`
   with `branch=stage1/section-uuids`, `profile=G4.2` (a CI compatibility alias
   for **GE-02**), and `regression_mode=profile`.
3. **Capture:** manually start `GE-02 Manual Graph Snapshot and Incremental
   Review` from `main`. Enter a repository-relative knowledge-graph JSON path.
   The default `examples/graph_engine/ge02_demo_graph.json` is strictly a
   synthetic example; it is *not a scientific source*.
4. Leave `persist_state=false` for a preview and downloadable state ZIP. This
   state disappears after the GitHub artifact retention period.
5. Set `persist_state=true` **explicitly** to commit the graph state to the
   development branch. This requires `contents: write` permission and a branch
   that allows GitHub Actions bot pushes. A fast-forward conflict or branch
   protection error fails without rewriting upstream history. The resulting
   state survives ephemeral runners because it is version-controlled.
6. No workflow has a `push` trigger. The job is started manually; choosing
   `persist_state=true` permits a *write during that manually started run*.

## Reuse with real documents

Provide a real `core.knowledge_graph` JSON export as the input. GE-02 detects
changed nodes and graph relations and identifies dependent nodes for review.
The project-level document-section invalidation and actual re-writing
feedback loop remain GE-03 work. GE-02 does not claim these are fully integrated.

## Acceptance gates

- Original GE-01 graph entities round trip through a versioned graph store.
- Subsequent updates produce a replayable G3.2 graph evolution delta.
- Source/node changes identify potentially dependent elements requiring review.
- Corruption, dangling edges, forged authority, symlinks, stale HEAD, and
  concurrent/abandoned locks are rejected.
- Graph-state publication is atomic, reproducible, and idempotent.
- Manual CI runs focused and full-regression tests without push triggers.
