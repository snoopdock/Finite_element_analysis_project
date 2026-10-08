
"""Controlled vocabulary for G3 graph analysis."""

from enum import Enum


class AnalysisType(str, Enum):
    STRUCTURAL = "structural"
    TRAVERSAL = "traversal"
    DEPENDENCY = "dependency"
    PATH = "path"
    CENTRALITY = "centrality"


class AnalysisStatus(str, Enum):
    COMPLETED = "completed"
    NO_MATCH = "no_match"


class VerificationStatus(str, Enum):
    """Lifecycle/epistemic state of evidence.

    This enum is retained at its G3.0 import path for backward compatibility.
    G3.1 distinguishes this evidence state from ``VerificationDecision``:
    evidence can be validated while an obligation is refuted, and corroborated
    evidence does not by itself imply a policy violation.
    """

    PROPOSED = "proposed"
    OBSERVED = "observed"
    CORROBORATED = "corroborated"
    VALIDATED = "validated"
    REJECTED = "rejected"
    INCONCLUSIVE = "inconclusive"
    STALE = "stale"


class TraversalDirection(str, Enum):
    OUTGOING = "outgoing"
    INCOMING = "incoming"
    BOTH = "both"
