"""Authenticate optional AE-02.1 change-impact scope for an AE-03 experiment."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from audit_engine.semantic_audit.ae01.publication import canonical, sha


@dataclass(frozen=True)
class VerifiedImpact:
    record: dict[str, Any]
    def to_dict(self) -> dict[str, Any]:
        plan = self.record['impact_plan']
        return {'comparison_sha256': self.record['comparison_sha256'],
                'plan_sha256': plan['plan_sha256'],
                'previous_generation': plan['previous_generation'],
                'current_generation': plan['current_generation'],
                'completeness': plan['completeness'],
                'truncated': plan['truncated']}


def verified_impact(before_output: Path | str, after_output: Path | str, *,
                    before_generation: str | None = None,
                    after_generation: str | None = None) -> VerifiedImpact:
    """Recompute AE-02 from independently sealed AE-01 generations; no trust in supplied JSON."""
    from audit_engine.semantic_audit.ae02.service import compare_generations
    record = compare_generations(before_output, after_output,
                                 before_generation=before_generation,
                                 after_generation=after_generation)
    plan = record['impact_plan']
    if sha(canonical({k: v for k, v in plan.items() if k != 'plan_sha256'})) != plan['plan_sha256']:
        raise ValueError('AE-02.1 impact plan digest mismatch')
    if sha(canonical({k: v for k, v in record.items() if k != 'comparison_sha256'})) != record['comparison_sha256']:
        raise ValueError('AE-02 generation comparison digest mismatch')
    return VerifiedImpact(record)
