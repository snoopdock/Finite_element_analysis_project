"""Deterministic comparison between audit generations."""
from dataclasses import dataclass

@dataclass(frozen=True)
class AuditDelta:
    source_changed: bool
    graph_changed: bool
    findings_changed: bool
    previous_generation: str
    current_generation: str

def compare_snapshots(previous, current):
    return AuditDelta(
        previous.source_manifest_hash != current.source_manifest_hash,
        previous.graph_hash != current.graph_hash,
        previous.finding_hash != current.finding_hash,
        previous.generation_id,
        current.generation_id,
    )
