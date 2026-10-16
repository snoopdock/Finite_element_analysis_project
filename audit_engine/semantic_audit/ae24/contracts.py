"""AE-24: bounded, language-independent contract admission to the canonical SemanticGraph.

Evidence bytes are caller-provided, not executed. A hash only binds bytes, not an
upstream identity. Proposed/neural relationships are quarantined, not promoted.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Mapping

from audit_engine.semantic_audit.core.semantic_graph import SemanticGraph, SemanticNode, SemanticEdge
from audit_engine.semantic_audit.ae13.admission import validate_graph
from audit_engine.semantic_audit.graph.analysis.identity import graph_fingerprint

SCHEMA = 'ae24/semantic-contracts/v1'
MAX_ENTITIES = 2000
MAX_ASSERTIONS = 12000
MAX_SOURCES = 2000
MAX_BYTES = 12_000_000
MAX_SOURCE_BYTES = 2_000_000
ENTITY_TYPES = frozenset({'Component', 'Artifact', 'Action', 'Check'})
ENDPOINTS = {
    'PRODUCES': ('Component', 'Artifact'),
    'CONSUMES': ('Component', 'Artifact'),
    'PERFORMS': ('Component', 'Action'),
    'FORBIDS': ('Component', 'Action'),
    'DEPENDS_ON': ('Component', 'Component'),
    'REQUIRES_CHECK': ('Component', 'Check'),
    'HAS_CHECK': ('Component', 'Check'),
}
ORIGINS = frozenset({'declared', 'observed', 'candidate'})
INTERFACE_KEYS = frozenset({'format', 'schema_id', 'meaning_id', 'producer', 'producer_occurrence'})
DIGEST = re.compile(r'^[0-9a-f]{64}$')


class ContractError(ValueError):
    """Input is not an admissible and source-bound semantic contract."""


def canonical(value: Any) -> bytes:
    try:
        return (json.dumps(value, sort_keys=True, ensure_ascii=False,
                           separators=(',', ':'), allow_nan=False) + '\n').encode('utf-8')
    except (TypeError, ValueError, OverflowError) as exc:
        raise ContractError('Noncanonical contract data') from exc


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _nonempty(value: Any, what: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 256 or value.strip() != value:
        raise ContractError(f'Invalid {what}')
    return value


def _object_keys(value: Any, allowed: set, required: set, what: str):
    if not isinstance(value, dict) or set(value) - allowed or not required <= set(value):
        raise ContractError(f'Invalid {what} keys')


def _bounded_json(value: Any) -> bytes:
    data = canonical(value)
    if len(data) > MAX_BYTES:
        raise ContractError('Contract exceeds byte budget')
    # deepcopy-by-value: detach from mutable caller structures
    return data


@dataclass(frozen=True)
class Admission:
    contract_digest: str
    graph_digest: str
    graph: SemanticGraph
    source_digests: tuple[tuple[str, str], ...]
    proposed_count: int
    status: str = 'evidence_bound_contract_admission_not_behavioral_verification'


def admit(contract: dict, source_bytes: Mapping[str, bytes]) -> Admission:
    """Admit exact declared/observed relations, quarantine unverified candidates.

    A source file hash proves only consistency with the bytes supplied here.
    It does not authenticate the producer of those bytes or the truth of an
    extracted assertion. Authoritative graph mutation is not performed.
    """
    encoded = _bounded_json(contract)
    _object_keys(contract, {'schema_version', 'namespace', 'entities', 'assertions', 'sources', 'coverage', 'policies'},
                 {'schema_version', 'namespace', 'entities', 'assertions', 'sources'}, 'contract')
    if contract['schema_version'] != SCHEMA:
        raise ContractError('Unsupported semantic contract schema')
    _nonempty(contract['namespace'], 'namespace')
    entities, assertions, sources = contract['entities'], contract['assertions'], contract['sources']
    coverage = contract.get('coverage', [])
    policies = contract.get('policies', [])
    if not all(isinstance(x, list) for x in (entities, assertions, sources, coverage, policies)):
        raise ContractError('Contract collections must be lists')
    if len(entities) > MAX_ENTITIES or len(assertions) > MAX_ASSERTIONS or len(sources) > MAX_SOURCES:
        raise ContractError('Semantic contract budget exceeded')
    if not isinstance(source_bytes, Mapping):
        raise ContractError('Source evidence must be a mapping')
    source_ids = set()
    source_digests = []
    for src in sources:
        _object_keys(src, {'id', 'sha256'}, {'id', 'sha256'}, 'source')
        sid = _nonempty(src['id'], 'source id')
        if sid in source_ids:
            raise ContractError('Duplicate evidence source identifier')
        source_ids.add(sid)
        if not isinstance(src['sha256'], str) or not DIGEST.fullmatch(src['sha256']):
            raise ContractError('Invalid evidence digest')
        if sid not in source_bytes:
            raise ContractError(f'Missing exact evidence bytes for {sid}')
        data = source_bytes[sid]
        if not isinstance(data, bytes) or len(data) > MAX_SOURCE_BYTES or sha(data) != src['sha256']:
            raise ContractError(f'Evidence byte mismatch for {sid}')
        source_digests.append((sid, src['sha256']))
    if set(source_bytes) != source_ids:
        raise ContractError('Unexpected source evidence')
    kinds = {}
    graph = SemanticGraph()
    for ent in entities:
        _object_keys(ent, {'id', 'kind', 'source_id'}, {'id', 'kind', 'source_id'}, 'entity')
        eid = _nonempty(ent['id'], 'entity id')
        if (eid in kinds or not isinstance(ent['kind'], str) or ent['kind'] not in ENTITY_TYPES
                or not isinstance(ent['source_id'], str) or ent['source_id'] not in source_ids):
            raise ContractError('Duplicate entity or unsupported entity type')
        kinds[eid] = ent['kind']
        graph.add_node(SemanticNode(eid, ent['kind'], {}, {'contract_namespace': contract['namespace'], 'source_id': ent['source_id']}))
    seen_assertions = set()
    proposals = 0
    for item in assertions:
        _object_keys(item, {'id', 'subject', 'predicate', 'object', 'origin', 'source_id', 'attributes'},
                     {'id', 'subject', 'predicate', 'object', 'origin', 'source_id'}, 'assertion')
        aid = _nonempty(item['id'], 'assertion id')
        if aid in seen_assertions:
            raise ContractError('Duplicate source occurrence identity')
        seen_assertions.add(aid)
        subject, target, predicate = item['subject'], item['object'], item['predicate']
        if (not isinstance(predicate, str) or predicate not in ENDPOINTS
                or not isinstance(subject, str) or not isinstance(target, str)
                or kinds.get(subject) != ENDPOINTS[predicate][0] or kinds.get(target) != ENDPOINTS[predicate][1]):
            raise ContractError(f'Invalid typed relationship in {aid}')
        if (not isinstance(item['origin'], str) or item['origin'] not in ORIGINS
                or not isinstance(item['source_id'], str) or item['source_id'] not in source_ids):
            raise ContractError('Unsupported origin or unbound source witness')
        attrs = item.get('attributes', {})
        if not isinstance(attrs, dict) or set(attrs) - INTERFACE_KEYS:
            raise ContractError('Unknown assertion attributes')
        if predicate not in {'PRODUCES', 'CONSUMES'} and attrs:
            raise ContractError('Only artifact interfaces may carry interface attributes')
        if predicate == 'PRODUCES' and 'producer' in attrs:
            raise ContractError('Producer is implicit on the producing edge')
        if predicate != 'CONSUMES' and ('producer' in attrs or 'producer_occurrence' in attrs):
            raise ContractError('Producer selectors are valid only for CONSUMES')
        if 'producer_occurrence' in attrs and 'producer' not in attrs:
            raise ContractError('Producer occurrence requires an explicit producer entity')
        for key, value in attrs.items():
            _nonempty(value, f'interface {key}')
        if 'producer' in attrs and kinds.get(attrs['producer']) != 'Component':
            raise ContractError('Producer selector is not a component')
        if item['origin'] == 'candidate':
            proposals += 1
        # Candidate assertions remain in the graph for retrieval, but reasoners
        # must never treat them as a trusted declared/observed fact.
        graph.add_edge(SemanticEdge(subject, target, predicate, dict(attrs), {
            'ae13_occurrence_id': aid, 'source_id': item['source_id'],
            'origin': item['origin'], 'admission': 'candidate_only' if item['origin'] == 'candidate' else 'source_bound_observation',
        }))
    seen_policies = set()
    for rule in policies:
        _object_keys(rule, {'id', 'kind', 'source_id'}, {'id', 'kind', 'source_id'}, 'policy')
        rid = _nonempty(rule['id'], 'policy identity')
        if (rid in seen_policies or rule['kind'] != 'acyclic_dependencies'
                or not isinstance(rule['source_id'], str) or rule['source_id'] not in source_ids):
            raise ContractError('Unsupported, duplicate or unbound policy')
        seen_policies.add(rid)
    seen_coverage = set()
    for record in coverage:
        _object_keys(record, {'component', 'relation', 'source_id', 'complete'},
                     {'component', 'relation', 'source_id', 'complete'}, 'coverage')
        if not isinstance(record['component'], str) or not isinstance(record['relation'], str):
            raise ContractError('Invalid coverage component or relation identity')
        key = (record['component'], record['relation'])
        if (key in seen_coverage or kinds.get(record['component']) != 'Component'
                or record['relation'] not in {'HAS_CHECK'}):
            raise ContractError('Invalid or duplicate coverage scope')
        seen_coverage.add(key)
        if (not isinstance(record['source_id'], str) or record['source_id'] not in source_ids
                or type(record['complete']) is not bool):
            raise ContractError('Invalid coverage evidence or completeness flag')
        # Explicit completeness is a SOURCE CLAIM, not proof that all real-world
        # relationships were observed. The audit report must repeat this caveat.
    validate_graph(graph)
    return Admission(sha(encoded), graph_fingerprint(graph), graph,
                     tuple(sorted(source_digests)), proposals)


def verify_admission(contract: dict, sources: Mapping[str, bytes], claimed: Admission) -> bool:
    """Exact source replay; identity equality alone is not evidence validation."""
    expected = admit(contract, sources)
    if not isinstance(claimed, Admission):
        raise ContractError('Invalid admission object')
    if (expected.contract_digest != claimed.contract_digest or expected.graph_digest != claimed.graph_digest
            or expected.source_digests != claimed.source_digests or expected.proposed_count != claimed.proposed_count
            or expected.graph.to_dict() != claimed.graph.to_dict()):
        raise ContractError('Admission does not match exact source replay')
    return True


def to_graph_assertions(admission: Admission, *, include_candidates: bool = False):
    """Read-only detached records; preserve parallel edge occurrence identities."""
    validate_graph(admission.graph)
    if graph_fingerprint(admission.graph) != admission.graph_digest:
        raise ContractError('Mutated graph cannot be read as admitted source')
    return [dict(subject=e.source_id, predicate=e.relation_type, object=e.target_id,
                 attributes=dict(e.attributes), metadata=dict(e.metadata))
            for e in admission.graph.edges
            if include_candidates or e.metadata.get('origin') != 'candidate']
