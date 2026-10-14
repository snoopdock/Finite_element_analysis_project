"""AE-05 human review journal: AE-04 evidence-bound, replayable, fail closed.

The record is NOT an authentication mechanism, a software correctness proof,
 or an automated adjudication service. Actor labels are unverified assertions.
"""
from __future__ import annotations
import copy
import json
from pathlib import Path
from typing import Any

from audit_engine.semantic_audit.ae01.publication import canonical, sha, _no_symlink_components
from audit_engine.semantic_audit.ae04 import verify_publication
from audit_engine.semantic_audit.evolution.memory import AuditLongTermMemory

SCHEMA = 'ae05/review_journal/v1'
GENESIS = 'ae05/genesis/v1'
ACTIONS = frozenset({'acknowledge', 'requires_action', 'dispute'})


def _hex64(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(ch in '0123456789abcdef' for ch in value)


def _campaign(output: Path | str, before_output: Path | str, after_output: Path | str,
              *, mutation_root: Path | None = None, replay_mutation: bool = False) -> dict:
    # Verify complete sealed AE-04 publication, and thus its AE-01/AE-02/AE-03
    # dependencies, before reading the named content-addressed campaign.
    receipt = verify_publication(output, before_output=before_output, after_output=after_output,
                                 mutation_root=mutation_root, replay_mutation=replay_mutation)
    name = receipt['generation']
    file = Path(output) / 'generations' / name / 'campaign.json'
    _no_symlink_components(file)
    data = file.read_bytes()
    record = json.loads(data)
    if record['campaign_sha256'] != receipt['campaign_sha256'] or sha(canonical(record)) != sha(data):
        raise ValueError('Campaign bytes changed after independent publication verification')
    return record


def _id(campaign_hash: str, kind: str, payload: dict) -> str:
    return sha(canonical({'campaign_sha256': campaign_hash, 'kind': kind, 'payload': payload}))


def _obligations(campaign: dict) -> list[dict]:
    digest = campaign['campaign_sha256']
    obligations = []
    for task in campaign['review']['tasks']:
        key = {'module': task['module'], 'priority': task['priority'],
               'reasons': task['reasons'], 'occurrence_ids': task['occurrence_ids'],
               'finding_ids': task['finding_ids'], 'source_files': task['source_files']}
        allowed = sorted(set(task['occurrence_ids'] + task['finding_ids'] + [digest]))
        obligations.append({'id': _id(digest, 'source_task', key), 'kind': 'source_task',
                            'module': task['module'], 'priority': task['priority'],
                            'reasons': list(task['reasons']), 'evidence_refs': allowed,
                            'source_files': list(task['source_files']),
                            'required_action': 'requires_action' if task['priority'] in ('P0','P1') else 'any'})
    # Campaign-level review is never omitted (even when there are zero source tasks).
    # This is crucial for a missing mutation record or a truncated result.
    cstatus = campaign['decision']['status']
    guard = {'decision': cstatus, 'campaign_sha256': digest,
             'truncated': bool(campaign['review']['truncated']),
             'mutation_status': campaign['mutation']['status']}
    obligations.append({'id': _id(digest, 'campaign_gate', guard), 'kind': 'campaign_gate',
                        'module': None, 'priority': 'P1' if cstatus != 'bounded_architecture_policy_pass' else 'P2',
                        'reasons': list(campaign['decision']['reasons']) or ['bounded_policy_scope_review'],
                        'evidence_refs': [digest], 'source_files': [],
                        'required_action': 'requires_action' if cstatus != 'bounded_architecture_policy_pass' else 'any'})
    obligations.sort(key=lambda x: (x['kind'], x['priority'], x['module'] or '', x['id']))
    if len({x['id'] for x in obligations}) != len(obligations):
        raise ValueError('Duplicated evidence-bound review obligation')
    return obligations


def _state(packet: dict, events: list[dict]) -> dict:
    obligations = {row['id']: row for row in packet['obligations']}
    latest = {}
    prev = sha(canonical({'genesis': GENESIS, 'campaign': packet['campaign_sha256']}))
    for index, item in enumerate(events, 1):
        if not isinstance(item, dict) or set(item) != {
            'campaign_sha256','sequence','obligation_id','action','actor',
            'note','evidence_refs','previous_hash','event_sha256'}:
            raise ValueError('Malformed review journal event')
        if item['campaign_sha256'] != packet['campaign_sha256'] or item['sequence'] != index or item['previous_hash'] != prev:
            raise ValueError('Review event sequence, campaign binding, or hash chain mismatch')
        row = obligations.get(item['obligation_id'])
        if row is None:
            raise ValueError('Unknown or stale review obligation')
        if item['action'] not in ACTIONS:
            raise ValueError('Unknown review action')
        if row['required_action'] == 'requires_action' and item['action'] == 'acknowledge':
            raise ValueError('A P0/P1 or incomplete campaign cannot be acknowledged as completed')
        if not isinstance(item['actor'], str) or not 1 <= len(item['actor'].strip()) <= 120 or item['actor'] != item['actor'].strip():
            raise ValueError('Invalid actor label')
        if not isinstance(item['note'], str) or not 1 <= len(item['note'].strip()) <= 2000 or item['note'] != item['note'].strip():
            raise ValueError('Human review must include a substantive note')
        refs = item['evidence_refs']
        if (not isinstance(refs, list) or not refs or refs != sorted(set(refs)) or
                not set(refs) <= set(row['evidence_refs'])):
            raise ValueError('Review evidence references are not in the sealed campaign')
        unsigned = {k:v for k,v in item.items() if k != 'event_sha256'}
        if sha(canonical(unsigned)) != item['event_sha256']:
            raise ValueError('Review event content hash mismatch')
        prev = item['event_sha256']
        latest[item['obligation_id']] = item['action']
    outstanding = sorted(set(obligations) - set(latest))
    needs_action = sorted(k for k,v in latest.items() if v != 'acknowledge')
    bounded = (packet['decision_status'] == 'bounded_architecture_policy_pass' and
               not outstanding and not needs_action and
               all(row['required_action'] == 'any' for row in obligations.values()))
    status = ('pending_human_review' if outstanding else
              'review_recorded_with_open_actions' if needs_action else
              'bounded_review_recorded' if bounded else 'review_recorded_not_a_policy_pass')
    return {'status': status, 'bounded_review_recorded': bounded,
            'general_correctness_certified': False,
            'outstanding_obligations': outstanding, 'open_action_obligations': needs_action,
            'reviewed_count': len(latest), 'total_obligations': len(obligations),
            'journal_head_sha256': prev}


def _memory(events: list[dict], campaign_sha256: str) -> dict:
    memory = AuditLongTermMemory()
    for event in events:
        memory.append_artifact(artifact_type='ae05_review_event',
                               artifact_id=event['obligation_id'],
                               snapshot_id=campaign_sha256, payload=event)
    return memory.to_dict()


def _assemble(packet: dict, events: list[dict]) -> dict:
    record = {'schema': SCHEMA, 'packet': copy.deepcopy(packet),
              'events': copy.deepcopy(events), 'state': _state(packet, events),
              'g3_memory': _memory(events, packet['campaign_sha256'])}
    record['review_sha256'] = sha(canonical(record))
    return record


def start_review(campaign_output: Path | str, before_output: Path | str,
                 after_output: Path | str, *, mutation_root: Path | None = None,
                 replay_mutation: bool = False) -> dict:
    campaign = _campaign(campaign_output, before_output, after_output,
                         mutation_root=mutation_root, replay_mutation=replay_mutation)
    packet = {'campaign_sha256': campaign['campaign_sha256'],
              'campaign_publication': 'ae04-'+campaign['campaign_sha256'][:32],
              'previous_generation_id': campaign['previous']['generation_id'],
              'current_generation_id': campaign['current']['generation_id'],
              'decision_status': campaign['decision']['status'],
              'architecture_clean_claim_within_scope': campaign['decision']['architecture_clean_claim_within_scope'],
              'obligations': _obligations(campaign),
              'rules': {'reviewer_authority': 'unverified_human_label',
                        'nonpassing_audit_must_not_be_promoted': True,
                        'review_events_do_not_certify_software_correctness': True}}
    return _assemble(packet, [])


def append_event(record: dict, obligation_id: str, action: str, actor: str, note: str,
                 *, evidence_refs: list[str] | None = None) -> dict:
    # Caller must have verified record with verify_review before updating it;
    # publication adapter does so under a lock and independently rechecks output.
    original = copy.deepcopy(record)
    packet = original['packet']
    matches = [o for o in packet['obligations'] if o['id'] == obligation_id]
    if len(matches) != 1:
        raise ValueError('Unknown review obligation')
    row = matches[0]
    refs = evidence_refs if evidence_refs is not None else row['evidence_refs']
    event = {'campaign_sha256': packet['campaign_sha256'], 'sequence': len(original['events'])+1,
             'obligation_id': obligation_id, 'action': action, 'actor': actor,
             'note': note, 'evidence_refs': sorted(set(refs)),
             'previous_hash': original['state']['journal_head_sha256']}
    event['event_sha256'] = sha(canonical(event))
    return _assemble(packet, original['events'] + [event])


def verify_review(record: dict, campaign_output: Path | str, before_output: Path | str,
                  after_output: Path | str, *, mutation_root: Path | None = None,
                  replay_mutation: bool = False) -> dict:
    if not isinstance(record, dict) or set(record) != {
        'schema','packet','events','state','g3_memory','review_sha256'} or record['schema'] != SCHEMA:
        raise ValueError('Invalid AE-05 review record schema')
    if record['review_sha256'] != sha(canonical({k:v for k,v in record.items() if k!='review_sha256'})):
        raise ValueError('Review record hash mismatch')
    expected = start_review(campaign_output, before_output, after_output,
                            mutation_root=mutation_root, replay_mutation=replay_mutation)
    if canonical(record['packet']) != canonical(expected['packet']):
        raise ValueError('Review campaign changed, or obligation evidence was altered')
    recomputed = _assemble(expected['packet'], record['events'])
    if canonical(recomputed) != canonical(record):
        raise ValueError('Review journal, state, or G3 memory disagrees with independent replay')
    # G3 content-addressed memory imported and reconstructed, not merely JSON hashed.
    mirrored = AuditLongTermMemory.from_dict(record['g3_memory'])
    if canonical(mirrored.to_dict()) != canonical(record['g3_memory']):
        raise ValueError('G3 review memory is not canonical')
    return {'status': 'verified', 'review_sha256': record['review_sha256'],
            'campaign_sha256': record['packet']['campaign_sha256'],
            'decision': record['state']['status'], 'journal_events': len(record['events']),
            'general_correctness_certified': False}
