"""AE-27 controlled, language-agnostic neurosymbolic proposal gateway."""
from .bridge import (
    SCHEMA,
    ADJUDICATION_SCHEMA,
    DECISIONS,
    LINK_KINDS,
    ProposalError,
    validate_proposal,
    symbolic_probe,
    symbolic_probe_set,
    adjudicate,
    verify_adjudication,
)

__all__ = [
    "SCHEMA",
    "ADJUDICATION_SCHEMA",
    "DECISIONS",
    "LINK_KINDS",
    "ProposalError",
    "validate_proposal",
    "symbolic_probe",
    "symbolic_probe_set",
    "adjudicate",
    "verify_adjudication",
]
