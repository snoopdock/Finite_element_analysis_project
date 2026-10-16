"""AE-25: language-agnostic structural reasoning on admitted semantic relationships.

Deterministic, bounded, fully witnessed, non-monotonic conclusions are scoped
strictly to source-submitted facts. No runtime, OWL-DL, or neural proof claims.
"""
from __future__ import annotations

from collections import defaultdict, deque
from typing import Any, Mapping

from audit_engine.semantic_audit.graph.analysis.identity import graph_fingerprint
from audit_engine.semantic_audit.ae13.admission import validate_graph
from audit_engine.semantic_audit.ae24.contracts import (
    admit, verify_admission, Admission, canonical, sha, ContractError,
)

SCHEMA = 'ae25/semantic-invariant-analysis/v1'
RULES = (
    'AE25.R1.INTERFACE_COMPATIBILITY',
    'AE25.R2.RESPONSIBILITY_BOUNDARY',
    'AE25.R3.REQUIRED_CHECK_COVERAGE',
    'AE25.R4.DEPENDENCY_ACYCLIC',
)
MAX_ISSUES = 12000
MAX_VISITS = 25000


class ReasoningError(ValueError):
    """Invalid admitted input, unbounded inference, or unverifiable report."""


def _witness(edge):
    return edge.metadata['ae13_occurrence_id']


def _record(rule: str, subject: str, target: str, label: str, witnesses, *, extra=None):
    item = {'rule_id': rule, 'subject': subject, 'target': target,
            'kind': label, 'witness_occurrences': sorted(set(witnesses)),
            'detail': extra or {}}
    item['id'] = 'ae25:' + sha(canonical(item))[:32]
    return item


def _active(admission: Admission):
    """Exclude all proposals even if their named relations would otherwise match."""
    out = defaultdict(list)
    for edge in admission.graph.edges:
        if edge.metadata['origin'] != 'candidate':
            out[(edge.relation_type, edge.source_id, edge.target_id)].append(edge)
    return out


def _cycles(admission: Admission):
    """Return witnessed cycles, each canonicalized by smallest node ID.

    This detects *some* cycles sufficient to demonstrate violation. It does
    not claim exhaustive enumeration of all cycles in a multigraph.
    """
    graph = defaultdict(list)
    for edge in admission.graph.edges:
        if edge.relation_type == 'DEPENDS_ON' and edge.metadata.get('origin') != 'candidate':
            graph[edge.source_id].append((edge.target_id, _witness(edge)))
    for key in graph:
        graph[key].sort()
    color = {}
    seen = set()
    found = []
    visits = 0
    for root in sorted({n.node_id for n in admission.graph.nodes if n.entity_type == 'Component'}):
        if root in color:
            continue
        stack = [(root, iter(graph.get(root, ())), None)]
        color[root] = 1
        visits += 1
        while stack:
            if visits > MAX_VISITS:
                raise ReasoningError('Dependency traversal resource budget exceeded')
            node, iterator, entering_edge = stack[-1]
            try:
                target, occurrence = next(iterator)
            except StopIteration:
                color[node] = 2
                stack.pop()
                continue
            if target not in color:
                color[target] = 1
                visits += 1
                stack.append((target, iter(graph.get(target, ())), occurrence))
            elif color[target] == 1:
                positions = [i for i, frame in enumerate(stack) if frame[0] == target]
                at = positions[0]
                chain = [frame[0] for frame in stack[at:]] + [target]
                witnesses = [frame[2] for frame in stack[at+1:]] + [occurrence]
                identity = tuple(sorted(set(chain)))
                if identity not in seen:
                    seen.add(identity)
                    found.append((chain, witnesses))
    return found


def impact(admission: Admission, changed_component: str) -> dict:
    """Conservative upstream dependents, not proof of behavioral change."""
    validate_graph(admission.graph)
    if graph_fingerprint(admission.graph) != admission.graph_digest:
        raise ReasoningError('Impact requires unchanged admitted graph')
    if changed_component not in {n.node_id for n in admission.graph.nodes if n.entity_type == 'Component'}:
        raise ReasoningError('Unknown component')
    reverse = defaultdict(list)
    for edge in admission.graph.edges:
        if edge.relation_type == 'DEPENDS_ON' and edge.metadata.get('origin') != 'candidate':
            reverse[edge.target_id].append((edge.source_id, _witness(edge)))
    queue = deque([changed_component])
    visited = {changed_component}
    witnesses = set()
    while queue:
        target = queue.popleft()
        for src, occ in sorted(reverse.get(target, ())):
            witnesses.add(occ)
            if src not in visited:
                visited.add(src)
                queue.append(src)
                if len(visited) > MAX_VISITS:
                    raise ReasoningError('Impact traversal budget exceeded')
    return {'changed_component': changed_component, 'possibly_affected_components': sorted(visited - {changed_component}),
            'supporting_occurrences': sorted(witnesses), 'effect_is_not_proven': True}


def analyze(contract: dict, sources: Mapping[str, bytes]) -> dict[str, Any]:
    """Replay source evidence, then check typed semantic assertions and contracts.

    A finding here means *a witnessed conflict in supplied relations*. It is
    NOT a runtime defect, a causally verified finding, or an authenticated fact.
    """
    admission = admit(contract, sources)
    active = _active(admission)
    issues, unknowns = [], []
    def issue(rule, subject, target, detail, supporting):
        if len(issues) >= MAX_ISSUES:
            raise ReasoningError('Issue budget exceeded')
        issues.append(_record(rule, subject, target, 'structural_conflict', supporting, extra=detail))
    def unknown(rule, subject, target, reason, supporting):
        if len(unknowns) >= MAX_ISSUES:
            raise ReasoningError('Unknown budget exceeded')
        unknowns.append(_record(rule, subject, target, 'incomplete', supporting, extra={'reason': reason}))
    # R1: a consumer explicitly bound to a producer is not permitted to silently
    # match an unrelated producer. Absent/ambiguous bindings must stay unknown.
    producers = defaultdict(list)
    for (relation, component, artifact), records in active.items():
        if relation == 'PRODUCES':
            producers[artifact].extend(records)
    for (relation, consumer, artifact), consumes in sorted(active.items()):
        if relation != 'CONSUMES':
            continue
        for consume in consumes:
            choices = producers.get(artifact, [])
            selected_id = consume.attributes.get('producer')
            selected_occurrence = consume.attributes.get('producer_occurrence')
            if selected_id is not None:
                choices = [p for p in choices if p.source_id == selected_id]
            elif len({p.source_id for p in choices}) > 1:
                unknown(RULES[0], consumer, artifact, 'ambiguous_producer_selection', [_witness(consume)] + [_witness(x) for x in choices])
                continue
            if selected_occurrence is not None:
                choices = [p for p in choices if _witness(p) == selected_occurrence]
            # Parallel source occurrences are not inherently ambiguous, but
            # several DISTINCT interface contracts for the same producer are.
            distinct_interfaces = {tuple(p.attributes.get(k) for k in ('format', 'schema_id', 'meaning_id')) for p in choices}
            if selected_occurrence is None and len(distinct_interfaces) > 1:
                unknown(RULES[0], consumer, artifact, 'ambiguous_producer_contract_versions',
                        [_witness(consume)] + [_witness(x) for x in choices])
                continue
            if not choices:
                unknown(RULES[0], consumer, artifact, 'unobserved_or_missing_producer', [_witness(consume)])
                continue
            values = {}
            for key in ('format', 'schema_id', 'meaning_id'):
                wanted = consume.attributes.get(key)
                if wanted is None:
                    unknown(RULES[0], consumer, artifact, 'consumer_contract_unspecified:' + key, [_witness(consume)])
                    continue
                if any(producer.attributes.get(key) is None for producer in choices):
                    unknown(RULES[0], consumer, artifact, 'producer_contract_unspecified:' + key, [_witness(consume)] + [_witness(x) for x in choices])
                    continue
                conflicting = [producer for producer in choices if producer.attributes[key] != wanted]
                if conflicting:
                    values[key] = {'expected': wanted, 'actual': sorted(set(p.attributes[key] for p in conflicting))}
            if values:
                issue(RULES[0], consumer, artifact, {'incompatible_fields': values},
                      [_witness(consume)] + [_witness(x) for x in choices])
    # R2: only a DECLARED prohibition plus OBSERVED action constitutes conflict.
    for (relation, component, action), forbids in sorted(active.items()):
        if relation != 'FORBIDS':
            continue
        declared = [e for e in forbids if e.metadata.get('origin') == 'declared']
        performed = [e for e in active.get(('PERFORMS', component, action), []) if e.metadata.get('origin') == 'observed']
        if declared and performed:
            issue(RULES[1], component, action, {'observed_vs_declared': True},
                  [_witness(e) for e in declared + performed])
    # R3: an absent check is never a violation without declared coverage completeness.
    coverage = {(r['component'], r['relation']): r for r in contract.get('coverage', [])}
    for (relation, component, check), requires in sorted(active.items()):
        if relation != 'REQUIRES_CHECK':
            continue
        if any(e.metadata.get('origin') == 'observed' for e in active.get(('HAS_CHECK', component, check), ())):
            continue
        record = coverage.get((component, 'HAS_CHECK'))
        if record and record['complete']:
            issue(RULES[2], component, check, {'coverage_is_source_claim_not_external_proof': True,
                   'coverage_source_id': record['source_id']}, [_witness(x) for x in requires])
        else:
            unknown(RULES[2], component, check, 'check_coverage_not_established', [_witness(x) for x in requires])
    # R4: absence of an explicit policy cannot make a dependency cycle a violation.
    acyclic = [p for p in contract.get('policies', []) if p['kind'] == 'acyclic_dependencies']
    if acyclic:
        for chain, supporting in _cycles(admission):
            issue(RULES[3], chain[0], chain[-1], {'cycle_node_ids': chain,
                 'policy_ids': sorted(p['id'] for p in acyclic),
                 'policy_source_ids': sorted(p['source_id'] for p in acyclic)}, supporting)
    # Candidate assertions are retained as hypotheses but never rule witnesses.
    if admission.proposed_count:
        unknown('AE25.META.CANDIDATE_QUARANTINE', contract['namespace'], 'candidate',
                'unverified_candidate_assertions_excluded', [])
    issues.sort(key=lambda x: (x['rule_id'], x['id']))
    unknowns.sort(key=lambda x: (x['rule_id'], x['id']))
    status = ('structural_conflicts_in_supplied_evidence' if issues else
              'incomplete' if unknowns else 'no_conflicts_in_admitted_relationships_only')
    output = {
        'schema_version': SCHEMA, 'contract_sha256': admission.contract_digest,
        'graph_fingerprint': admission.graph_digest,
        'source_digests': [{'id': key, 'sha256': value} for key, value in admission.source_digests],
        'rule_ids': list(RULES), 'issues': issues, 'unknowns': unknowns,
        'issues_count': len(issues), 'unknown_count': len(unknowns),
        'status': status, 'candidate_count': admission.proposed_count,
        'authority': {
            'source_bytes_verified': True,
            'source_origin_authenticated': False,
            'source_assertion_truth_verified': False,
            'runtime_causality_verified': False,
            'external_clean_assurance_established': False,
            'automatic_graph_mutation_permitted': False,
            'neural_proposals_accepted_as_facts': False,
        },
    }
    output['report_sha256'] = sha(canonical(output))
    return output


def verify_report(contract: dict, sources: Mapping[str, bytes], claimed: Any) -> dict:
    """Independent source replay. Rehashing altered results cannot satisfy it."""
    if not isinstance(claimed, dict) or claimed != analyze(contract, sources):
        raise ReasoningError('Source-replayed semantic reasoning report mismatch')
    return {'status': 'source_replayed', 'report_sha256': claimed['report_sha256'],
            'verified_root_cause': False, 'verified_clean': False}
