"""Source-located finding reconciliation and manual-only disposition history.

A vanished finding is only *not observed* within a complete, equivalent policy
scope; this is not a proof that the underlying software has become correct.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from audit_engine.semantic_audit.ae01.publication import sha, canonical

TRANSITIONS = {
    None: frozenset({'observed'}),
    'observed': frozenset({'verified', 'rejected'}),
    'verified': frozenset({'accepted', 'rejected'}),
    'accepted': frozenset({'resolved', 'reopened'}),
    'resolved': frozenset({'reopened'}),
    'reopened': frozenset({'verified', 'rejected'}),
    'rejected': frozenset({'reopened'}),
}


@dataclass
class FindingLifecycleManager:
    state: dict[str, str] = field(default_factory=dict)
    history: list[dict] = field(default_factory=list)

    def transition(self, finding_id: str, new_state: str, evidence_id: str, *, actor: str) -> str:
        if not all(isinstance(x, str) and x.strip() for x in (finding_id, new_state, evidence_id, actor)):
            raise ValueError('Every transition requires finding, status, evidence and actor')
        old = self.state.get(finding_id)
        if new_state not in TRANSITIONS.get(old, ()):
            raise ValueError(f'Invalid lifecycle transition {old} -> {new_state}')
        event = {'finding': finding_id, 'from': old, 'to': new_state,
                 'evidence': evidence_id, 'actor': actor, 'sequence': len(self.history) + 1}
        event['event_sha256'] = sha(canonical(event))
        self.state[finding_id] = new_state
        self.history.append(event)
        return new_state


def _witness_key(entry: dict, occurrences: dict[str, dict]) -> tuple:
    witness = entry['witness']
    fact = occurrences[witness['occurrence_id']]
    # The source hash is deliberately not part of the location identity.
    # Target and context are part of the identity, unlike call spelling.
    return (entry['finding']['rule_id'], witness['source_id'], witness['line'],
            witness['column'], fact['target'], tuple(fact['context']))


def _findings(generation) -> dict[tuple, dict]:
    occurrences = {i['id']: i for i in generation.facts['imports']}
    keys = {}
    for entry in generation.report['findings']:
        key = _witness_key(entry, occurrences)
        if key in keys:
            raise ValueError('Ambiguous duplicate finding location')
        keys[key] = entry
    return keys


def reconcile_findings(before, after, *, policy_changed: bool) -> list[dict]:
    left, right = _findings(before), _findings(after)
    after_complete = after.report['assurance_completeness'] == 'complete_within_declared_scope'
    events = []
    for key in sorted(left.keys() | right.keys()):
        prior, current = left.get(key), right.get(key)
        if prior and current:
            status = 'revalidated_with_changed_evidence' if (
                prior['finding']['receipt_id'] != current['finding']['receipt_id'] or
                prior['witness']['source_sha256'] != current['witness']['source_sha256']) else 'persists'
        elif current:
            status = 'new_under_changed_policy' if policy_changed else 'new_verified_observation'
        elif not after_complete or policy_changed:
            status = 'unassessed_after_change'
        else:
            status = 'not_observed_in_complete_audit'
        events.append({
            'identity': sha(canonical(key)), 'rule_id': key[0], 'source_id': key[1],
            'line': key[2], 'column': key[3], 'target': key[4], 'context': list(key[5]),
            'status': status,
            'previous_receipt_id': prior['finding']['receipt_id'] if prior else None,
            'current_receipt_id': current['finding']['receipt_id'] if current else None,
            'previous_finding_id': prior['finding']['finding_id'] if prior else None,
            'current_finding_id': current['finding']['finding_id'] if current else None,
        })
    return events
