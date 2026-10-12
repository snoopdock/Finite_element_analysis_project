"""GE-04: read-only, evidence-bound graph-impact to document-section review plans.

Only explicitly declared links to stable section UUIDs are used. Text similarity,
legacy ``key_equations`` and inferred citations NEVER create authoritative links.
Neither review proposals nor source hashes establish scientific correctness.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import uuid
from typing import Any

from audit_engine.semantic_audit.graph.native_impact_analysis import analyze, GE03Error
from core.document_model import SCHEMA_VERSION as DOCUMENT_SCHEMA_VERSION
from audit_engine.semantic_audit.graph.domain_integration import from_scientific_graph, _read_json, GraphDomainError
from audit_engine.semantic_audit.graph.persistent_domain_state import (
    PersistentDomainGraphStore, GraphStoreError, _input_path, canonical, sha, parse
)

SCHEMA = 'ge04-bound-section-review-plan/v1'
BINDING_SCHEMA = 'ge04-explicit-section-bindings/v1'
DIGEST = re.compile(r'^[0-9a-f]{64}$')
MAX_INPUT = 4_000_000
MAX_LINKS = 10000
MAX_SECTIONS = 10000
MAX_REPORT = 8_000_000


class GE04Error(ValueError):
    """Malformed, ungrounded or unsafe science-to-document reference."""


def _uuid(value: Any, name: str) -> str:
    if not isinstance(value, str):
        raise GE04Error(f'{name} must be canonical UUID')
    try:
        normalized = str(uuid.UUID(value))
    except (ValueError, TypeError, AttributeError) as exc:
        raise GE04Error(f'Invalid {name}') from exc
    if value != normalized:
        raise GE04Error(f'Noncanonical {name}')
    return value


def _hash(value: Any, name: str) -> str:
    if not isinstance(value, str) or DIGEST.fullmatch(value) is None:
        raise GE04Error(f'Invalid {name}')
    return value


def _safe_read(repo: Path, relative: str) -> bytes:
    """Open only regular, repository-local JSON without symbolic links."""
    try:
        path = _input_path(repo, relative)
    except (OSError, GraphStoreError, ValueError) as exc:
        raise GE04Error(f'Unsafe or missing repository input: {relative!r}') from exc
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise GE04Error('Symlinked input is prohibited')
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_INPUT:
            raise GE04Error('Input must be a regular bounded file')
        raw = os.read(fd, MAX_INPUT + 1)
        if len(raw) != info.st_size:
            raise GE04Error('Input changed during read')
        return raw
    finally:
        os.close(fd)


def _json(repo: Path, relative: str) -> tuple[dict[str, Any], bytes]:
    raw = _safe_read(repo, relative)
    try:
        value = parse(raw)  # GE-02 parser rejects duplicate keys and non-finite numbers
    except (GraphStoreError, ValueError) as exc:
        raise GE04Error('Invalid input JSON') from exc
    if not isinstance(value, dict):
        raise GE04Error('Document and bindings must be JSON objects')
    return value, raw


def _sections(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Read persisted *semantic* sections with stable IDs, never generate IDs."""
    if document.get('type') != 'document' or not isinstance(document.get('children'), list):
        raise GE04Error('A persisted typed Document with children is required')
    _uuid(document.get('document_id'), 'document_id')
    if type(document.get('version')) is not int or document['version'] != DOCUMENT_SCHEMA_VERSION:
        raise GE04Error('Unsupported persisted document schema version')
    if not isinstance(document.get('metadata'), dict):
        raise GE04Error('Document metadata must be an object')
    children = document['children']
    if not children or len(children) > MAX_SECTIONS:
        raise GE04Error('Document has no sections or exceeds budget')
    result: dict[str, dict[str, Any]] = {}
    for item in children:
        if not isinstance(item, dict) or item.get('type') != 'section':
            raise GE04Error('Document contains an invalid section')
        sid = _uuid(item.get('section_id'), 'section_id')
        if sid in result:
            raise GE04Error('Duplicate document section ID')
        title = item.get('title')
        if not isinstance(title, str) or not title.strip() or len(title) > 500:
            raise GE04Error('Missing or excessive section title')
        if not isinstance(item.get('children'), list):
            raise GE04Error('Section children must be a list')
        if any(not isinstance(child, dict) or not isinstance(child.get('type'), str)
               for child in item['children']):
            raise GE04Error('Malformed persisted section child')
        result[sid] = {'section_id': sid, 'title': title}
    return result


def _validate_bindings(data: dict[str, Any], *, document: dict, document_raw: bytes,
                       head: str, compared_snapshot: str | None,
                       known_nodes: set[str], sections: dict[str, dict]) -> list[dict[str, str]]:
    expected = {'schema_version', 'document_id', 'document_sha256',
                'expected_store_head_sha256', 'expected_compared_snapshot_sha256', 'links'}
    if set(data) != expected or data.get('schema_version') != BINDING_SCHEMA:
        raise GE04Error('Unexpected section binding contract')
    if _uuid(data['document_id'], 'binding document ID') != document['document_id']:
        raise GE04Error('Binding refers to another document')
    if _hash(data['document_sha256'], 'document SHA-256') != hashlib.sha256(document_raw).hexdigest():
        raise GE04Error('Document changed after bindings were prepared')
    if _hash(data['expected_store_head_sha256'], 'expected store HEAD') != head:
        raise GE04Error('Binding is stale for the persisted graph generation')
    target = data['expected_compared_snapshot_sha256']
    if compared_snapshot is None:
        if target is not None:
            raise GE04Error('Unexpected candidate snapshot binding in no-candidate mode')
    elif _hash(target, 'compared snapshot') != compared_snapshot:
        raise GE04Error('Binding is stale for the compared graph')
    raw_links = data['links']
    if not isinstance(raw_links, list) or not raw_links or len(raw_links) > MAX_LINKS:
        raise GE04Error('Explicit section bindings required and bounded')
    links = []
    seen = set()
    for item in raw_links:
        if not isinstance(item, dict) or set(item) != {'section_id', 'graph_node_id', 'relation', 'rationale'}:
            raise GE04Error('Malformed explicit section link')
        sid = _uuid(item['section_id'], 'linked section')
        node = item['graph_node_id']
        if sid not in sections or not isinstance(node, str) or node not in known_nodes:
            raise GE04Error('Dangling section or scientific graph reference')
        if item['relation'] != 'EXPLICITLY_REFERENCES':
            raise GE04Error('Only structural, explicit references are permitted')
        rationale = item['rationale']
        if not isinstance(rationale, str) or not 4 <= len(rationale.strip()) <= 1000:
            raise GE04Error('Explicit link rationale required')
        key = (sid, node)
        if key in seen:
            raise GE04Error('Duplicate explicit section link')
        seen.add(key)
        links.append({'section_id': sid, 'graph_node_id': node,
                      'relation': 'EXPLICITLY_REFERENCES', 'rationale': rationale.strip()})
    return sorted(links, key=lambda item: (item['section_id'], item['graph_node_id']))


def plan(repo: str | Path, *, document_path: str, bindings_path: str,
         mode: str = 'candidate', knowledge_graph: str | None = None,
         store: str = '.graph-state/scientific') -> dict[str, Any]:
    """Produce a verifiable, read-only section review plan from native GE-03 analysis."""
    repo = Path(repo).resolve(strict=True)
    impact = analyze(repo, mode=mode, knowledge_graph=knowledge_graph, store=store)
    state_store = PersistentDomainGraphStore(repo / store)
    baseline = state_store.current_view()
    if baseline is None:
        raise GE04Error('No verified scientific graph state')
    known_nodes = {node.node_id for node in baseline.graph.nodes}
    if mode == 'candidate':
        if not knowledge_graph:
            raise GE04Error('Candidate graph is required')
        source = _input_path(repo, knowledge_graph)
        candidate = from_scientific_graph(_read_json(source))
        known_nodes.update(node.node_id for node in candidate.graph.nodes)
    document, doc_raw = _json(repo, document_path)
    bindings, binding_raw = _json(repo, bindings_path)
    sections = _sections(document)
    links = _validate_bindings(
        bindings, document=document, document_raw=doc_raw,
        head=impact['store_head_sha256'],
        compared_snapshot=impact['compared_snapshot_sha256'],
        known_nodes=known_nodes, sections=sections)
    candidates = impact['review_candidates']
    if any(not isinstance(c, dict) or not isinstance(c.get('node_id'), str) or
           not isinstance(c.get('distance'), int) or c['distance'] < 0 or
           c['node_id'] not in known_nodes for c in candidates):
        raise GE04Error('Invalid GE-03 review frontier')
    impact_nodes = {c['node_id'] for c in candidates}
    if len(impact_nodes) != len(candidates):
        raise GE04Error('Duplicate GE-03 review candidate')
    by_section: dict[str, list[dict[str, Any]]] = {}
    for link in links:
        if link['graph_node_id'] not in impact_nodes:
            continue
        candidate = next(c for c in candidates if c['node_id'] == link['graph_node_id'])
        by_section.setdefault(link['section_id'], []).append({
            'graph_node_id': link['graph_node_id'],
            'distance': candidate['distance'],
            'graph_reason': candidate['reason'],
            'relation': link['relation'],
        })
    tasks = []
    for sid, triggers in sorted(by_section.items()):
        triggers.sort(key=lambda t: (t['distance'], t['graph_node_id']))
        tasks.append({
            'section_id': sid,
            'title': sections[sid]['title'],
            'task': 'human_scientific_review',
            'minimum_structural_distance': min(t['distance'] for t in triggers),
            'triggers': triggers,
            'approval_permitted': False,
            'automatic_rewrite_permitted': False,
        })
    mapped_nodes = {link['graph_node_id'] for link in links}
    unmapped = sorted(impact_nodes - mapped_nodes)
    if impact['status'] in ('no_prior_transition', 'no_structural_change'):
        status = 'no_change_to_review'
    elif not tasks:
        status = 'blocked_no_section_mapping'
    elif unmapped:
        status = 'partial_mapping_requires_review'
    else:
        status = 'review_plan_ready'
    result = {
        'schema_version': SCHEMA,
        'status': status,
        'impact_status': impact['status'],
        'impact_report_sha256': impact['report_sha256'],
        'graph_store_head_sha256': impact['store_head_sha256'],
        'graph_store_generation': impact['store_generation'],
        'compared_snapshot_sha256': impact['compared_snapshot_sha256'],
        'document_id': document['document_id'],
        'document_path': document_path,
        'document_sha256': hashlib.sha256(doc_raw).hexdigest(),
        'bindings_path': bindings_path,
        'bindings_sha256': hashlib.sha256(binding_raw).hexdigest(),
        'explicit_binding_count': len(links),
        'review_candidate_count': len(candidates),
        'section_review_count': len(tasks),
        'section_review_tasks': tasks,
        'unmapped_graph_node_ids': unmapped,
        'mapping_basis': 'explicit_versioned_section_bindings_only',
        'scientific_truth_established': False,
        'automatic_approval_permitted': False,
        'automatic_document_modification_permitted': False,
        'persisted_graph_mutated': False,
    }
    raw = canonical(result)
    if len(raw) > MAX_REPORT:
        raise GE04Error('Review plan exceeds budget')
    result['report_sha256'] = sha(raw)
    return result


def _write_new_report(dest: str | Path, repo: Path, report: dict) -> None:
    path = Path(os.path.abspath(dest))
    if path == repo or repo in path.parents or any(x.is_symlink() for x in (path, *path.parents)):
        raise GE04Error('Output must be outside source repository and not symlinked')
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    except OSError as exc:
        raise GE04Error('Output already exists or is unsafe') from exc
    with os.fdopen(fd, 'wb') as handle:
        handle.write(canonical(report))
        handle.flush()
        os.fsync(handle.fileno())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='GE-04 explicit FEM section review planning')
    parser.add_argument('--repository', required=True)
    parser.add_argument('--mode', choices=['candidate', 'latest-transition'], default='candidate')
    parser.add_argument('--knowledge-graph')
    parser.add_argument('--document', required=True)
    parser.add_argument('--bindings', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args(argv)
    repo = Path(args.repository).resolve(strict=True)
    report = plan(repo, document_path=args.document, bindings_path=args.bindings,
                  mode=args.mode, knowledge_graph=args.knowledge_graph)
    _write_new_report(args.output, repo, report)
    print(json.dumps({key: report[key] for key in ('status', 'section_review_count',
                    'review_candidate_count', 'report_sha256')}, sort_keys=True))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (GE04Error, GE03Error, GraphStoreError, GraphDomainError, OSError,
            ValueError, KeyError, TypeError) as exc:
        print(f'GE-04 rejected input: {exc}', file=sys.stderr)
        sys.exit(2)
