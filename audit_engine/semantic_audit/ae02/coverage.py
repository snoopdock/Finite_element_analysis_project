"""Auditable rule coverage derived from sealed AE-01 execution records."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum


class CoverageStatus(str, Enum):
    VERIFIED = 'verified'
    INCOMPLETE = 'incomplete'
    NOT_APPLICABLE = 'not_applicable'
    NOT_ASSESSED = 'not_assessed'


@dataclass(frozen=True)
class CoverageEntry:
    rule_id: str
    source_modules_evaluated: int
    observations: int
    obligations: int
    receipts: int
    findings: int
    status: CoverageStatus
    reasons: tuple[str, ...]

    def to_dict(self) -> dict:
        return {'rule_id': self.rule_id, 'source_modules_evaluated': self.source_modules_evaluated,
                'observations': self.observations, 'obligations': self.obligations,
                'receipts': self.receipts, 'findings': self.findings,
                'status': self.status.value, 'reasons': list(self.reasons)}


@dataclass(frozen=True)
class CoverageMatrix:
    entries: tuple[CoverageEntry, ...] = ()

    def add(self, entry: CoverageEntry) -> 'CoverageMatrix':
        if any(item.rule_id == entry.rule_id for item in self.entries):
            raise ValueError('Duplicate coverage rule identifier')
        return CoverageMatrix(self.entries + (entry,))

    def clean_claim_allowed(self) -> bool:
        return bool(self.entries) and all(
            e.status is CoverageStatus.VERIFIED and e.observations > 0 and e.observations == e.obligations == e.receipts
            and e.findings == 0 for e in self.entries)

    def to_dict(self) -> dict:
        return {'entries': [entry.to_dict() for entry in self.entries],
                'clean_claim_allowed': self.clean_claim_allowed()}


def from_generation(generation) -> CoverageMatrix:
    report, rows = generation.report, generation.executions
    reasons = {issue['kind'] for issue in report['issues']}
    obligations = sum(len(row['rule_execution']['obligations']) for row in rows)
    receipts = sum(len(row['rule_execution']['receipts']) for row in rows)
    observations = report['applicable_observations']
    if any(row['rule_execution']['reason'] != 'executed' for row in rows):
        reasons.add('rule_execution_skipped')
    if observations != obligations or obligations != receipts:
        reasons.add('coverage_count_mismatch')
    if report['assurance_completeness'] != 'complete_within_declared_scope':
        reasons.add('assurance_inconclusive')
    if observations == 0:
        status = CoverageStatus.NOT_APPLICABLE if not rows else CoverageStatus.NOT_ASSESSED
    elif reasons:
        status = CoverageStatus.INCOMPLETE
    else:
        status = CoverageStatus.VERIFIED
    rule_id = generation.policy['rule']['rule_id']
    entry = CoverageEntry(rule_id, len(rows), observations, obligations, receipts,
                          len(report['findings']), status, tuple(sorted(reasons)))
    matrix = CoverageMatrix().add(entry)
    # Never allow coverage to elevate a weaker AE-01 verdict.
    if matrix.clean_claim_allowed() != bool(report['verified_compliance']):
        raise ValueError('Policy coverage disagrees with AE-01 verified compliance')
    return matrix
