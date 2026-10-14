"""AE-02 verified, content-addressed views of sealed AE-01 audit generations.

Historical generations are verified against their own sealed bytes, not against
current source bytes (which by definition may have changed). AE-01's independent
source/graph/receipt contract is reused, not weakened or replaced.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any
from audit_engine.semantic_audit.verification.immutable_payload import freeze

from audit_engine.semantic_audit.ae01.publication import (
    _no_symlink_components, _verify_contract, canonical, sha, verify,
)

GENERATION_PATTERN = re.compile(r'ae01-[0-9a-f]{32}\Z')
EXPECTED_FILES = frozenset({
    'manifest.json', 'source_facts.json', 'graph.json', 'policy_graph.json',
    'rule_executions.json', 'policy.json', 'report.json',
})


@dataclass(frozen=True)
class AuditSnapshot:
    """Content-derived generation identity; never embeds a wall-clock value."""

    generation_id: str
    source_manifest_hash: str
    source_digest: str
    graph_hash: str
    finding_hash: str
    policy_hash: str
    publication_seal_hash: str
    assurance_completeness: str

    def to_dict(self) -> dict[str, str]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class VerifiedGeneration:
    snapshot: AuditSnapshot
    manifest: dict[str, Any]
    facts: dict[str, Any]
    report: dict[str, Any]
    policy: dict[str, Any]
    executions: list[dict[str, Any]]
    policy_graph: dict[str, Any]

    def __post_init__(self) -> None:
        # AE-01 returns ordinary JSON dictionaries; once a generation passes
        # detached verification, prevent downstream callers from modifying
        # facts/receipts while still treating them as verified evidence.
        for name in ('manifest', 'facts', 'report', 'policy', 'executions', 'policy_graph'):
            object.__setattr__(self, name, freeze(getattr(self, name)))


def _read(folder: Path, name: str) -> Any:
    return json.loads((folder / name).read_bytes())


def load_generation(output: Path | str, generation_id: str | None = None, *,
                    source_root: Path | None = None, policy_file: Path | None = None) -> VerifiedGeneration:
    """Independently verify one *sealed* AE-01 generation before using its facts.

    When generation_id is omitted, require the current completed LATEST pointer.
    A named historical generation is allowed even if the latest attempt failed.
    Current source/policy rechecks are optional, and meaningful only if their
    supplied paths represent the audited generation's inputs.
    """
    output = Path(output).absolute()
    _no_symlink_components(output)
    if generation_id is None:
        latest = _read(output, 'LATEST.json')
        if latest.get('status') != 'completed':
            raise ValueError('Latest AE-01 audit attempt is not completed')
        generation_id = latest.get('generation')
        # AE-01 verifies the trusted latest pointer as well as generation seal.
        verify(output, source_root=source_root, policy_file=policy_file)
    if not isinstance(generation_id, str) or not GENERATION_PATTERN.fullmatch(generation_id):
        raise ValueError('Unsafe or malformed AE-01 generation identifier')
    folder = output / 'generations' / generation_id
    _no_symlink_components(folder)
    if not folder.is_dir():
        raise ValueError('AE-01 generation directory is missing')
    names = {p.name for p in folder.iterdir()}
    if names != EXPECTED_FILES | {'SEAL.json'}:
        raise ValueError('Unexpected or missing AE-01 generation artifacts')
    seal_path = folder / 'SEAL.json'
    _no_symlink_components(seal_path)
    seal_raw = seal_path.read_bytes()
    seal = json.loads(seal_raw)
    if seal.get('schema') != 'ae01/artifact_seal/v1' or set(seal.get('artifacts', {})) != EXPECTED_FILES:
        raise ValueError('Invalid AE-01 artifact seal schema or membership')
    for name, digest in seal['artifacts'].items():
        path = folder / name
        _no_symlink_components(path)
        if sha(path.read_bytes()) != digest:
            raise ValueError(f'Artifact checksum mismatch: {name}')
    manifest = _read(folder, 'manifest.json')
    facts = _read(folder, 'source_facts.json')
    policy = _read(folder, 'policy.json')
    executions = _read(folder, 'rule_executions.json')
    report = _read(folder, 'report.json')
    policy_graph = _read(folder, 'policy_graph.json')
    if report.get('schema') != 'ae01/report/v1' or report.get('run_id') != generation_id:
        raise ValueError('AE-01 generation report identity mismatch')
    if report.get('execution_status') != 'completed':
        raise ValueError('AE-01 generation was not completed')
    _verify_contract(folder, report, source_root=source_root, policy_file=policy_file)
    # This second boundary catches tampered source-fact payloads that are
    # sealed but do not correspond to occurrence witnesses in the report.
    if policy.get('sha256') != report['policy_sha256'] or policy['configuration']['policy_sha256'] != report['policy_sha256']:
        raise ValueError('Policy identity mismatch')
    if len(facts['imports']) != report['counts']['imports'] or len(facts['calls']) != report['counts']['calls'] or len(facts['functions']) != report['counts']['functions']:
        raise ValueError('Source fact counts disagree with sealed report')
    occurrence_ids = {i['id'] for i in facts['imports']}
    if len(occurrence_ids) != len(facts['imports']):
        raise ValueError('Duplicate source occurrence identity')
    # Cross-check the complete internal import model against G3's verified
    # policy graph. A newly re-sealed, altered source-fact target must not
    # produce fabricated 'unchanged dependency' conclusions.
    internal = {i['id']: i for i in facts['imports'] if i['status'] == 'internal'}
    policy_edges = {e['metadata']['occurrence_id']: e for e in policy_graph['edges'] if e['relation'] == 'IMPORTS'}
    if set(policy_edges) != set(internal):
        raise ValueError('Source import occurrences disagree with policy graph')
    included_hashes = {r['path']: r['sha256'] for r in manifest['files'] if r['status'] == 'included'}
    from audit_engine.semantic_audit.ae01.source import module_name
    for occurrence_id, imp in internal.items():
        edge = policy_edges[occurrence_id]
        witness = edge['metadata']
        if (edge['source'], edge['target']) != ('module:' + module_name(imp['file']), 'module:' + imp['target']):
            raise ValueError('Import resolution disagrees with verified policy graph')
        if (witness['source_id'], witness['source_sha256'], witness['line'], witness['column'], witness['context']) != (
                imp['file'], included_hashes[imp['file']], imp['line'], imp['column'], imp['context']):
            raise ValueError('Import source span/hash/context disagrees with policy graph')
    for row in report['findings']:
        occurrence_id = row['witness']['occurrence_id']
        if occurrence_id not in occurrence_ids:
            raise ValueError('Verified finding lacks a source import occurrence')
        occurrence = next(i for i in facts['imports'] if i['id'] == occurrence_id)
        if (occurrence['file'], occurrence['line'], occurrence['column'], occurrence['status']) != (
                row['witness']['source_id'], row['witness']['line'], row['witness']['column'], 'internal'):
            raise ValueError('Finding witness disagrees with source facts')
    snapshot = AuditSnapshot(
        generation_id=generation_id,
        source_manifest_hash=report['source_manifest_sha256'],
        source_digest=report['source_digest'],
        graph_hash=report['graph_fingerprint'],
        finding_hash=sha(canonical(report['findings'])),
        policy_hash=report['policy_sha256'],
        publication_seal_hash=sha(seal_raw),
        assurance_completeness=report['assurance_completeness'],
    )
    return VerifiedGeneration(snapshot, manifest, facts, report, policy, executions, policy_graph)
