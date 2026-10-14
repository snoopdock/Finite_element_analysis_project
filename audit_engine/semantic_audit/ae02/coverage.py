"""Policy coverage model for avoiding false-clean audits."""
from dataclasses import dataclass
from enum import Enum

class CoverageStatus(str, Enum):
    VERIFIED="verified"
    INCOMPLETE="incomplete"
    NOT_APPLICABLE="not_applicable"
    NOT_ASSESSED="not_assessed"

@dataclass(frozen=True)
class CoverageMatrix:
    entries: tuple = ()

    def add(self, rule, applicable, evaluated, status):
        return CoverageMatrix(self.entries + ((rule, applicable, evaluated, status),))

    def clean_claim_allowed(self):
        return all(e[3] == CoverageStatus.VERIFIED for e in self.entries)
