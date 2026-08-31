Stage 5 semantic claim-to-source verification

Implementation status
- Passage-aware semantic verifier added.
- Document-level verification is bounded by a per-cycle claim limit.
- Verification is disabled by default in config.yaml.
- Conflicting source judgments resolve conservatively to insufficient_evidence.
- Only cached/full source text is used for semantic verification; missing full text is insufficient evidence.
- Semantic review results are stored in state as last_semantic_review when enabled.

Important limitation
Semantic verification is an LLM judgment against selected source passages. It is not a formal proof of truth or entailment. Runtime execution and model-behavior validation remain required before enabling it by default.
