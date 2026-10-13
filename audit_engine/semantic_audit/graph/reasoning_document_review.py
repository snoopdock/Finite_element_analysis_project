"""G7.3: explicit, source-bound inferred-fact -> scientific document review.

Proof of a structural inference is not proof of scientific truth. Bindings are
editor-authored and version-bound. This module never alters repository state.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any

from audit_engine.semantic_audit.graph.reasoning_change_review import (
    G72Error, analyze as analyze_reasoning, verify as verify_reasoning,
)
from audit_engine.semantic_audit.graph.section_impact_integration import (
    GE04Error, _json as read_repository_json, _sections, _uuid, _hash,
)
from audit_engine.semantic_audit.graph.structural_reasoning import _read_bounded_json, _write_new
from audit_engine.semantic_audit.graph.persistent_domain_state import canonical, sha

SCHEMA = 'g7-reasoning-document-review/v1'
BINDING_SCHEMA = 'g7-explicit-inference-section-bindings/v1'
EVENT_KINDS = ('added', 'retracted', 'rewitnessed')
MAX_LINKS = 10000
MAX_REPORT_BYTES = 8_000_000


class G73Error(ValueError):
    """Invalid, stale or insufficiently grounded inference-to-section mapping."""


def _fact_key(fact: Any) -> tuple[str, str, str, str]:
    if not isinstance(fact, dict):
        raise G73Error('Inference fact must be an object')
    keys = ('rule_id', 'source_id', 'inferred_relation', 'target_id')
    if any(not isinstance(fact.get(k), str) or not fact[k] for k in keys):
        raise G73Error('Incomplete inference identity')
    return tuple(fact[k] for k in keys)


def _event_rows(change: dict[str, Any]) -> list[dict[str, Any]]:
    """Use EXACT verified G7.2 inference facts and preserve before/after proofs."""
    events = []
    for kind, field in [('added', 'added_inferences'),
                        ('retracted', 'retracted_inferences'),
                        ('rewitnessed', 'rewitnessed_inferences')]:
        for item in change[field]:
            if kind == 'rewitnessed':
                fact = item['fact']
                before_proof, after_proof = item['before'], item['after']
                if _fact_key(before_proof) != _fact_key(fact) or _fact_key(after_proof) != _fact_key(fact):
                    raise G73Error('Rewitnessed fact identity mismatch')
            elif kind == 'added':
                fact, before_proof, after_proof = item, None, item
            else:
                fact, before_proof, after_proof = item, item, None
            rule, source, relation, target = _fact_key(fact)
            events.append({
                'event_kind': kind,
                'fact': {'rule_id': rule, 'source_id': source,
                         'inferred_relation': relation, 'target_id': target},
                'before_witness_sha256': sha(canonical(before_proof)) if before_proof is not None else None,
                'after_witness_sha256': sha(canonical(after_proof)) if after_proof is not None else None,
            })
    events.sort(key=lambda e: (e['event_kind'], *_fact_key(e['fact'])))
    if len({(e['event_kind'], *_fact_key(e['fact'])) for e in events}) != len(events):
        raise G73Error('Duplicate reasoning-change events')
    return events


def _validate_bindings(bindings: dict, *, document: dict, document_raw: bytes,
                       change: dict, events: list[dict], sections: dict) -> list[dict]:
    expected = {'schema_version', 'document_id', 'document_sha256',
                'expected_store_head_sha256', 'expected_before_snapshot_sha256',
                'expected_after_snapshot_sha256', 'links'}
    if set(bindings) != expected or bindings['schema_version'] != BINDING_SCHEMA:
        raise G73Error('Unexpected G7.3 explicit binding contract')
    if _uuid(bindings['document_id'], 'binding document ID') != document['document_id']:
        raise G73Error('Binding document mismatch')
    if _hash(bindings['document_sha256'], 'document digest') != hashlib.sha256(document_raw).hexdigest():
        raise G73Error('Stale binding for changed document')
    for field, target in [('expected_store_head_sha256', 'verified_store_head_sha256'),
                          ('expected_before_snapshot_sha256', 'before_snapshot_sha256'),
                          ('expected_after_snapshot_sha256', 'after_snapshot_sha256')]:
        if _hash(bindings[field], field) != change[target]:
            raise G73Error('Stale binding for reasoning comparison: ' + field)
    raw = bindings['links']
    if not isinstance(raw, list) or len(raw) > MAX_LINKS:
        raise G73Error('Explicit bindings must be a bounded list')
    known = {_fact_key(e['fact']) for e in events}
    output, seen = [], set()
    for entry in raw:
        if not isinstance(entry, dict) or set(entry) != {'section_id', 'fact', 'relation', 'rationale'}:
            raise G73Error('Malformed inference-to-section link')
        sid = _uuid(entry['section_id'], 'section ID')
        if sid not in sections:
            raise G73Error('Dangling section link')
        if (not isinstance(entry['fact'], dict) or
                set(entry['fact']) != {'rule_id', 'source_id', 'inferred_relation', 'target_id'}):
            raise G73Error('Malformed inference fact identity')
        fact = _fact_key(entry['fact'])
        if fact not in known:
            raise G73Error('Binding references absent or unchanged inference')
        if entry['relation'] != 'EXPLICITLY_REVIEWS_INFERENCE':
            raise G73Error('Binding must explicitly review this inference')
        rationale = entry['rationale']
        if not isinstance(rationale, str) or not 4 <= len(rationale.strip()) <= 1000:
            raise G73Error('Human-editor rationale required')
        key = sid, fact
        if key in seen:
            raise G73Error('Duplicate inference-section binding')
        seen.add(key)
        output.append({'section_id': sid, 'fact': dict(zip(('rule_id','source_id','inferred_relation','target_id'), fact)),
                       'relation': entry['relation'], 'rationale': rationale.strip()})
    return sorted(output, key=lambda x: (x['section_id'], *_fact_key(x['fact'])))


def plan(repo: str | Path, *, document_path: str, bindings_path: str,
         mode: str = 'candidate', knowledge_graph: str | None = None,
         store: str = '.graph-state/scientific') -> dict[str, Any]:
    """Independently replay G7.2, authenticate explicit document/fact bindings."""
    repo = Path(repo).resolve(strict=True)
    change = analyze_reasoning(repo, mode=mode, knowledge_graph=knowledge_graph, store=store)
    # This is not a check of a claimed report: analyze_reasoning recomputes GE-02
    # history and G7.1's complete structural inference closure independently.
    if change['authority'] != {
        'scientific_truth_established': False, 'owl_dl_entailment_established': False,
        'automatic_approval_permitted': False, 'authoritative_graph_mutation_permitted': False,
        'automatic_document_edits_permitted': False,
    }:
        raise G73Error('Reasoning authority boundary violated')
    document, raw = read_repository_json(repo, document_path)
    sections = _sections(document)
    bindings, raw_bindings = read_repository_json(repo, bindings_path)
    events = _event_rows(change)
    links = _validate_bindings(bindings, document=document, document_raw=raw,
                               change=change, events=events, sections=sections)
    links_by_fact: dict[tuple, list[dict]] = {}
    for link in links:
        links_by_fact.setdefault(_fact_key(link['fact']), []).append(link)
    grouped: dict[str, list[dict]] = {}
    unmapped = []
    for event in events:
        refs = links_by_fact.get(_fact_key(event['fact']), [])
        if not refs:
            unmapped.append({'event_kind': event['event_kind'], 'fact': event['fact']})
        for link in refs:
            grouped.setdefault(link['section_id'], []).append({
                **event, 'binding_relation': link['relation'], 'editorial_rationale': link['rationale'],
            })
    tasks = [{
        'section_id': sid, 'title': sections[sid]['title'],
        'task': 'human_scientific_inference_review',
        'triggers': sorted(items, key=lambda x: (x['event_kind'], *_fact_key(x['fact']))),
        'approval_permitted': False, 'automatic_rewrite_permitted': False,
    } for sid, items in sorted(grouped.items())]
    if not events:
        status = 'no_inference_change'
    elif not tasks:
        status = 'blocked_no_explicit_inference_mapping'
    elif unmapped:
        status = 'partial_inference_mapping_requires_review'
    else:
        status = 'human_review_plan_ready'
    result = {
        'schema_version': SCHEMA,
        'status': status,
        'reasoning_change_status': change['status'],
        'reasoning_change_report_sha256': change['report_sha256'],
        'graph_store_head_sha256': change['verified_store_head_sha256'],
        'graph_store_generation': change['verified_store_generation'],
        'before_snapshot_sha256': change['before_snapshot_sha256'],
        'after_snapshot_sha256': change['after_snapshot_sha256'],
        'document_id': document['document_id'], 'document_path': document_path,
        'document_sha256': hashlib.sha256(raw).hexdigest(),
        'bindings_path': bindings_path,
        'bindings_sha256': hashlib.sha256(raw_bindings).hexdigest(),
        'explicit_binding_count': len(links),
        'reasoning_event_count': len(events),
        'added_inference_count': len(change['added_inferences']),
        'retracted_inference_count': len(change['retracted_inferences']),
        'rewitnessed_inference_count': len(change['rewitnessed_inferences']),
        'section_review_count': len(tasks),
        'section_review_tasks': tasks,
        'unmapped_inference_events': sorted(unmapped, key=lambda x: (x['event_kind'], *_fact_key(x['fact']))),
        'mapping_basis': 'explicit_versioned_inference_section_bindings_only',
        'authority': {'scientific_truth_established': False,
                      'owl_dl_entailment_established': False,
                      'automatic_approval_permitted': False,
                      'authoritative_graph_mutation_permitted': False,
                      'automatic_document_edits_permitted': False},
    }
    if len(canonical(result)) > MAX_REPORT_BYTES:
        raise G73Error('Reasoning-to-document report exceeds byte limit')
    result['report_sha256'] = sha(canonical(result))
    return result


def verify(repo: str | Path, report: Any, *, document_path: str, bindings_path: str,
           mode: str = 'candidate', knowledge_graph: str | None = None,
           store: str = '.graph-state/scientific') -> dict[str, Any]:
    if not isinstance(report, dict):
        raise G73Error('Expected report JSON object')
    expected = plan(repo, document_path=document_path, bindings_path=bindings_path,
                    mode=mode, knowledge_graph=knowledge_graph, store=store)
    if expected != report:
        raise G73Error('Independent source-bound inference-document replay mismatch')
    return {'status': 'verified', 'review_status': expected['status'],
            'reasoning_event_count': expected['reasoning_event_count'],
            'section_review_count': expected['section_review_count'],
            'unmapped_event_count': len(expected['unmapped_inference_events']),
            'report_sha256': expected['report_sha256']}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='G7.3 explicit reasoning-to-document review')
    parser.add_argument('action', choices=('run', 'verify'))
    parser.add_argument('--repository', required=True)
    parser.add_argument('--mode', choices=('candidate', 'latest-transition'), default='candidate')
    parser.add_argument('--knowledge-graph')
    parser.add_argument('--store', default='.graph-state/scientific')
    parser.add_argument('--document', required=True)
    parser.add_argument('--bindings', required=True)
    parser.add_argument('--report', required=True)
    args = parser.parse_args(argv)
    repo = Path(args.repository).resolve(strict=True)
    outfile = Path(os.path.abspath(args.report))
    if outfile == repo or repo in outfile.parents or any(p.is_symlink() for p in (outfile, *outfile.parents)):
        raise G73Error('Detached non-symlink report path required')
    options = dict(document_path=args.document, bindings_path=args.bindings,
                   mode=args.mode, knowledge_graph=args.knowledge_graph, store=args.store)
    if args.action == 'run':
        result = plan(repo, **options)
        _write_new(outfile, result)
        summary = {'status': result['status'], 'report_sha256': result['report_sha256'],
                   'reasoning_event_count': result['reasoning_event_count'],
                   'section_review_count': result['section_review_count']}
    else:
        summary = verify(repo, _read_bounded_json(outfile), **options)
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (G73Error, G72Error, GE04Error, OSError, ValueError, TypeError, KeyError) as exc:
        sys.stderr.write('G7.3 review rejected: ' + str(exc) + '\n')
        sys.exit(2)
