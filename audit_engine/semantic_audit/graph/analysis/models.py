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
    """Epistemic status of evidence used by an analysis result.

    G3 graph traversal can establish that an observation exists in the
    canonical semantic graph; it cannot by itself establish program behavior,
    scientific truth, or policy compliance.  Stronger states are reserved for
    later verification layers.
    """

    OBSERVED = "observed"
    CORROBORATED = "corroborated"
    VALIDATED = "validated"
    REJECTED = "rejected"


class TraversalDirection(str, Enum):
    OUTGOING = "outgoing"
    INCOMING = "incoming"
    BOTH = "both"
