"""Immutable audit generation snapshots.

AE-02 does not replace AE-01 publication. It consumes published evidence
and creates comparable audit generations.
"""
from dataclasses import dataclass
from pathlib import Path
import hashlib, json, time

@dataclass(frozen=True)
class AuditSnapshot:
    generation_id: str
    source_manifest_hash: str
    graph_hash: str
    finding_hash: str
    created_at: float

def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def create_snapshot(manifest, graph, findings):
    payloads = [
        json.dumps(manifest, sort_keys=True, default=str).encode(),
        json.dumps(graph, sort_keys=True, default=str).encode(),
        json.dumps(findings, sort_keys=True, default=str).encode(),
    ]
    mh, gh, fh = [_sha(x) for x in payloads]
    generation = _sha((mh+gh+fh).encode())[:32]
    return AuditSnapshot(generation, mh, gh, fh, time.time())
