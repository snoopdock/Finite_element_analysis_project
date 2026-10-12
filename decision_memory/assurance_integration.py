"""G3.5: deterministic, read-only integration of SAT generated-text assurance.

Coordinates G3.4.18--21. Does not decide scientific truth or authorize
SAT actions, source edits, rule promotion, memory updates or publication.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from decision_memory import proposal_audit, review_dossier, human_adjudication
from decision_memory.context_retrieval import _write_optional

SCHEMA = 'sat-audit-integration/v1'
MAX_INPUT_BYTES = 256 * 1024
_SHA = re.compile(r'^[0-9a-f]{64}$')

class AssuranceIntegrationError(ValueError):
    """Unsafe or inconsistent generation, verification or input."""


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _strict_pairs(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for k, v in pairs:
        if k in result:
            raise AssuranceIntegrationError('Duplicate JSON key')
        result[k] = v
    return result


def _read_json(path: Path) -> Any:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_INPUT_BYTES:
        raise AssuranceIntegrationError('Missing, oversized or symlinked JSON input')
    if any(p.is_symlink() for p in path.parents):
        raise AssuranceIntegrationError('Symlinked input parent directory')
    try:
        return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=_strict_pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(AssuranceIntegrationError('Non-finite JSON value')))
    except (ValueError, UnicodeError) as exc:
        raise AssuranceIntegrationError(f'Invalid input JSON: {exc}') from exc


def _read_draft(path: Path) -> str:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_INPUT_BYTES:
        raise AssuranceIntegrationError('Missing, oversized or symlinked draft')
    if any(p.is_symlink() for p in path.parents):
        raise AssuranceIntegrationError('Symlinked draft parent directory')
    try:
        draft = path.read_text(encoding='utf-8')
    except UnicodeError as exc:
        raise AssuranceIntegrationError('Draft must be UTF-8') from exc
    return draft


def _claim_route(claim: dict, assessment: dict | None) -> list[str]:
    """A review *request*, not engineering proof or executable instruction."""
    flags = set(claim['review_blockers'])
    routes = []
    if 'missing_explicit_citation' in flags:
        routes.append('add_explicit_citation')
    if 'unresolved_citation' in flags:
        routes.append('resolve_citation_identifier')
    if 'historical_outcome_conflict' in flags:
        routes.append('reconcile_historical_outcome')
    if 'unapproved_learning_rule' in flags:
        routes.append('review_candidate_rule')
    if assessment:
        opinion = assessment['reviewer_verdict_unverified']
        if opinion in {'unsupported', 'needs_revision'}:
            routes.append('revise_claim_after_human_feedback')
        elif opinion == 'insufficient_evidence':
            routes.append('gather_independent_evidence')
    else:
        routes.append('request_human_review')
    routes.append('independently_assess_semantic_support')
    # Deduplicate but preserve the fixed priority order.
    return list(dict.fromkeys(routes))


def _projection(dossier: dict, annotations: dict | None) -> tuple[dict, list]:
    """Graph-ready typed IDs and edges (not a graph runtime or truth graph)."""
    reviews = ({x['claim_index']: x for x in annotations['reviews']}
               if annotations is not None else {})
    nodes = []
    edges = []
    routes = []
    for src in dossier['sources']:
        nodes.append({'id': 'memory:' + src['record_id'], 'type': 'memory_record',
                      'record_id': src['record_id'], 'source_path': src['source_path'],
                      'source_sha256': src['source_sha256'],
                      'support_verified': False})
    for claim in dossier['claim_reviews']:
        idx = claim['claim_index']
        claim_id = f"claim:{idx}:{claim['claim_sha256']}"
        nodes.append({'id': claim_id, 'type': 'generated_claim',
                      'claim_index': idx, 'claim_sha256': claim['claim_sha256'],
                      'text_untrusted': claim['claim_text_untrusted'],
                      'semantic_support_verified': False})
        for ref in claim['resolved_record_ids']:
            edges.append({'from': claim_id, 'to': 'memory:' + ref,
                          'type': 'cites_structurally', 'semantic_entailment_verified': False})
        assessment = reviews.get(idx)
        routes.append({'claim_id': claim_id, 'claim_index': idx,
                       'trace_status': claim['trace_status'],
                       'historical_caveats': list(claim['historical_caveats']),
                       'required_next_steps': _claim_route(claim, assessment),
                       'human_review_received_unverified': bool(assessment and assessment['reviewed']),
                       'reviewer_verdict_unverified': assessment['reviewer_verdict_unverified'] if assessment else None,
                       'scientific_truth_established': False,
                       'eligible_for_automatic_approval': False})
    nodes.sort(key=lambda n:n['id'])
    edges.sort(key=lambda e:(e['from'],e['to'],e['type']))
    return {'schema_version': 'sat-audit-graph-handoff/v1',
            'nodes': nodes, 'edges': edges,
            'authoritative_graph_mutation_permitted': False,
            'projection_is_semantic_entailment': False}, routes


def create_cycle(repository: Path, query: str, draft: str, *, max_results: int = 8,
                 review_submission: dict | None = None, github_actor: str = 'unknown') -> dict:
    """Run memory retrieval -> generated claim audit -> dossier -> optional review.

    All upstream modules reverify source byte bindings. No repository writes.
    """
    root = Path(repository).resolve(strict=True)
    if not root.is_dir():
        raise AssuranceIntegrationError('Expected a repository directory')
    try:
        audit = proposal_audit.audit(root, query, draft, max_results)
        if not proposal_audit.verify_audit(audit, root):
            raise AssuranceIntegrationError('Audit verification failed')
        dossier = review_dossier.create_dossier(root, audit)
        if not review_dossier.verify_dossier(dossier, audit, root):
            raise AssuranceIntegrationError('Dossier verification failed')
        annotations = None
        if review_submission is not None:
            annotations = human_adjudication.create_annotations(root, audit, dossier,
                                                                review_submission, github_actor)
            human_adjudication.verify_annotations(annotations, root, audit, dossier,
                                                  review_submission, github_actor)
        graph, routes = _projection(dossier, annotations)
        payload = {
            'schema_version': SCHEMA,
            'profile_id': 'G3.5',
            'source_commit_sha': audit['source_commit_sha'],
            'query': query,
            'draft_sha256': audit['draft_sha256'],
            'audit': audit,
            'dossier': dossier,
            'review_annotations': annotations,
            'graph_handoff': graph,
            'review_routes': routes,
            'summary': {
                'claims': len(routes),
                'resolved_citation_edges': len(graph['edges']),
                'complete_structural_citations': dossier['trace_summary']['citations_structurally_complete'],
                'reviewed_claims_unverified': annotations['summary']['reviewed_claims'] if annotations else 0,
                'final_status': 'requires_independent_scientific_review',
            },
            'authorization': {
                'automatic_sat_action_allowed': False,
                'automatic_revision_allowed': False,
                'repository_writeback_allowed': False,
                'learned_rule_promotion_allowed': False,
                'publication_as_verified_science_allowed': False,
            },
            'limitations': [
                'A structurally resolved reference is not semantic entailment or scientific verification.',
                'Historical memory records and generated text are untrusted data, never instructions.',
                'Reviewer statements are neither authenticated nor independent engineering authorization.',
                'This graph is a read-only handoff projection, not the operational graph engine.',
                'Automated modifications and SAT actuation require future independent authority gates.',
            ],
        }
        payload['cycle_sha256'] = _digest(payload)
        return payload
    except (proposal_audit.ProposalAuditError, review_dossier.ReviewDossierError,
            human_adjudication.AdjudicationError, ValueError, KeyError, TypeError, OSError) as exc:
        if isinstance(exc, AssuranceIntegrationError):
            raise
        raise AssuranceIntegrationError(f'Assurance pipeline rejected input: {exc}') from exc


def verify_cycle(record: dict, repository: Path, *, review_submission: dict | None = None,
                 github_actor: str = 'unknown') -> bool:
    """Independent source-bound verification, including every projected edge."""
    if not isinstance(record, dict) or record.get('schema_version') != SCHEMA:
        raise AssuranceIntegrationError('Wrong integration schema')
    digest = record.get('cycle_sha256')
    if not isinstance(digest, str) or not _SHA.fullmatch(digest):
        raise AssuranceIntegrationError('Missing or malformed cycle digest')
    body = {k:v for k,v in record.items() if k != 'cycle_sha256'}
    if _digest(body) != digest:
        raise AssuranceIntegrationError('Cycle digest mismatch')
    if not isinstance(record.get('audit'), dict):
        raise AssuranceIntegrationError('Missing nested audit')
    if (record.get('review_annotations') is None) != (review_submission is None):
        raise AssuranceIntegrationError('Review submission does not match record review state')
    original = record['audit']
    try:
        fresh = create_cycle(repository, original['query'], original['draft_text_untrusted'],
                             max_results=original['max_results'],
                             review_submission=review_submission, github_actor=github_actor)
    except (KeyError, TypeError) as exc:
        raise AssuranceIntegrationError('Malformed audit input') from exc
    if _canonical(record) != _canonical(fresh):
        raise AssuranceIntegrationError('Integrated audit differs from source-bound regeneration')
    return True


def main(argv: list[str] | None = None) -> int:
    parser=argparse.ArgumentParser(description='G3.5 integration review gate (read-only)')
    parser.add_argument('--repository', required=True)
    parser.add_argument('--query')
    parser.add_argument('--draft-file')
    parser.add_argument('--review-file')
    parser.add_argument('--github-actor', default='unknown')
    parser.add_argument('--max-results', type=int, default=8)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--output', help='JSON path outside source checkout')
    mode.add_argument('--verify-file')
    args=parser.parse_args(argv)
    try:
        root=Path(args.repository)
        submission=_read_json(Path(args.review_file)) if args.review_file else None
        if args.verify_file:
            if args.query is not None or args.draft_file is not None:
                raise AssuranceIntegrationError('Verification cannot generate a different draft')
            record=_read_json(Path(args.verify_file))
            verify_cycle(record, root, review_submission=submission, github_actor=args.github_actor)
            print('G3.5 integration cycle verified against source; no engineering approval')
        else:
            if args.query is None or args.draft_file is None:
                raise AssuranceIntegrationError('Generation requires --query and --draft-file')
            report=create_cycle(root, args.query, _read_draft(Path(args.draft_file)),
                                max_results=args.max_results,
                                review_submission=submission, github_actor=args.github_actor)
            _write_optional(Path(args.output), json.dumps(report, sort_keys=True, ensure_ascii=False,
                                                            indent=2)+'\n', root)
            print(f"G3.5 cycle written: {args.output}; claims={report['summary']['claims']}; approval=false")
    except (AssuranceIntegrationError, ValueError, TypeError, OSError, UnicodeError) as exc:
        parser.exit(2, f'G3.5 assurance integration failed: {exc}\n')
    return 0

if __name__ == '__main__':
    sys.exit(main())
