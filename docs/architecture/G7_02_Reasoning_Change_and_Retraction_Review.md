# G7.2 — Source-Bound Reasoning Change and Retraction Review

## Purpose

G7.1 computes a finite, witnessed structural closure over one scientific graph. G7.2 **reconciles those results across a verified graph transition** to reveal which *structural inferences* are added, retracted, unchanged, or still present but supported by a different witness path.

This does **not** prove natural-language scientific assertions, OWL-DL entailment, or authority to modify scientific conclusions. A retracted G7 inference means it is no longer derivable from the current *explicit graph facts* with these two bounded rules; it does not mean the underlying research proposition is false.

## Native integrations

- GE-02: `PersistentDomainGraphStore.verify()` checks all reachable commits and content-addressed transitions. The newest verified state is the only accepted baseline.
- G7.1: `structural_reasoning.reason()` recomputes exact finite closure and witnessed paths for each graph snapshot. No inference cache is trusted as authority.
- GE-02 transition engine: `_transition()` computes the native graph-delta ID and structural review candidates. Recorded transitions in historical mode must equal independently recomputed transitions.
- Native `scientific_knowledge` domain and stable concept/proposition IDs are reused. No additional graph backend is created.

## Modes and state rules

| Mode | Before | After | Outcome |
|---|---|---|---|
| `candidate` | Verified GE-02 HEAD | User-specified repository-relative candidate JSON | Detached review; no persistence |
| `latest-transition` (generation 1) | Current verified graph | Current verified graph | `no_prior_transition`; **no invented history** |
| `latest-transition` (generation 2+) | Verified parent commit graph | Verified HEAD graph | Source-bound reasoning delta and verified persisted GE-02 transition |

The candidate workflow demonstration reparents a concept and is expected to report **one newly inferred and one retracted** proposition-to-ancestor association. Direct graph edges are not automatically recorded as inferred facts; G7.1's two rule definitions determine which facts enter the closure.

## Report semantics

- `added_inferences`: present only after the graph change.
- `retracted_inferences`: present only before the change.
- `rewitnessed_inferences`: same rule/source/relation/target remains derivable, but canonical source-witness path or witness-edge hashes have changed. This includes metadata-only support changes.
- `unchanged_inference_count`: matching facts with matching witnesses.
- `structural_review_candidates`: GE-02's native reverse dependency *review* frontier; not proof of implication.
- `native_graph_delta_id`: source-bound GE transition identifier.
- `before_reasoning_sha256`, `after_reasoning_sha256`: identities of independently replayed G7.1 reports.

Authority flags prohibit scientific approval, graph mutation, document edits and OWL-entailment claims. Reports use bounded deterministic JSON and an SHA-256 digest for tamper evidence, not digital signatures or external trust.

## Acceptance boundaries and limitations

- This is **full bounded closure recomputation**, not an optimized incremental inference cache. Recalculation is intentional: it allows the verifier to find missing and invented retractions independently.
- It is finite and limited by the G7.1 rule set and resource budgets. The vocabulary is not a general OWL reasoner.
- Missing domain-to-document links remain missing; GE-04 is the separate document-impact subsystem.
- Uploaded GitHub workflow artifacts have finite retention; persist evidence elsewhere if required for long-term audit.
- SHA-256 protects integrity when compared with a trusted source; it does not authenticate who authored repository content.

## Acceptance steps

1. Manually validate profile `G7.2` using the established dispatcher (`regression_mode=profile`).
2. Manually run `G7.2 Manual Reasoning Change and Retraction Review` in `candidate` mode using the included fixture; expect an added and a retracted structural fact.
3. Run `latest-transition` mode if desired; generation-1 state must report `no_prior_transition`, not fabricate changed proofs.
4. Verify the detached report and verification summary, and reject any auto-approval flag.
