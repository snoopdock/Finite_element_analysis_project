"""AE-26 language-independent semantic vocabulary and contract evolution."""
from .semantics import (
    SCHEMA, DIFF_SCHEMA, RELATION_SEMANTICS, CONCEPT_TYPES,
    SemanticModelError, SemanticEdgeView, SemanticSnapshot,
    validate_vocabulary, snapshot, semantic_projection, verify_snapshot,
    diff_contracts, verify_diff,
)
__all__ = [
    "SCHEMA", "DIFF_SCHEMA", "RELATION_SEMANTICS", "CONCEPT_TYPES",
    "SemanticModelError", "SemanticEdgeView", "SemanticSnapshot",
    "validate_vocabulary", "snapshot", "semantic_projection", "verify_snapshot",
    "diff_contracts", "verify_diff",
]
