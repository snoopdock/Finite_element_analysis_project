"""G7.3 acceptance: exact source/proof bindings, no fabricated section review."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import shutil

import pytest

from audit_engine.semantic_audit.graph.reasoning_change_review import analyze as reasoning_change, G72Error
from audit_engine.semantic_audit.graph.reasoning_document_review import (
    G73Error, _event_rows, plan, verify, _fact_key,
)
from audit_engine.semantic_audit.graph.section_impact_integration import GE04Error
from audit_engine.semantic_audit.graph.persistent_domain_state import GraphStoreError

SOURCE = Path(__file__).resolve().parents[2]
CANDIDATE = 'examples/graph_engine/g72_demo_reparented_graph.json'
DOCUMENT = 'examples/graph_engine/ge04_demo_document.json'
BINDINGS = 'examples/graph_engine/g73_demo_inference_section_bindings.json'


@pytest.fixture
def repo(tmp_path):
    (tmp_path / '.graph-state').mkdir()
    shutil.copytree(SOURCE / '.graph-state/scientific', tmp_path / '.graph-state/scientific')
    (tmp_path / 'examples/graph_engine').mkdir(parents=True)
    for name in (CANDIDATE, DOCUMENT, BINDINGS):
        target = tmp_path / name
        shutil.copy2(SOURCE / name, target)
    return tmp_path


def run(repo, **changes):
    options = dict(document_path=DOCUMENT, bindings_path=BINDINGS,
                   mode='candidate', knowledge_graph=CANDIDATE)
    options.update(changes)
    return plan(repo, **options)


def edit(repo, transform, name=BINDINGS):
    path = repo / name
    value = json.loads(path.read_text())
    transform(value)
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + '\n')


def refresh(repo):
    """Rebind an explicit file to the current verified comparison for test scenarios."""
    change = reasoning_change(repo, mode='candidate', knowledge_graph=CANDIDATE)
    doc = repo / DOCUMENT
    def apply(v):
        v['document_sha256'] = hashlib.sha256(doc.read_bytes()).hexdigest()
        v['expected_store_head_sha256'] = change['verified_store_head_sha256']
        v['expected_before_snapshot_sha256'] = change['before_snapshot_sha256']
        v['expected_after_snapshot_sha256'] = change['after_snapshot_sha256']
    edit(repo, apply)


def test_end_to_end_two_facts_two_sections(repo):
    result = run(repo)
    assert result['schema_version'] == 'g7-reasoning-document-review/v1'
    assert result['status'] == 'human_review_plan_ready'
    assert result['added_inference_count'] == 1
    assert result['retracted_inference_count'] == 1
    assert result['rewitnessed_inference_count'] == 0
    assert result['reasoning_event_count'] == 2
    assert result['section_review_count'] == 2
    assert result['unmapped_inference_events'] == []
    assert set(t['triggers'][0]['event_kind'] for t in result['section_review_tasks']) == {'added', 'retracted'}
    assert all(t['task'] == 'human_scientific_inference_review' for t in result['section_review_tasks'])
    assert all(not t['automatic_rewrite_permitted'] and not t['approval_permitted'] for t in result['section_review_tasks'])
    assert all(v is False for v in result['authority'].values())
    assert verify(repo, result, document_path=DOCUMENT, bindings_path=BINDINGS,
                  mode='candidate', knowledge_graph=CANDIDATE)['status'] == 'verified'


def test_determinism_and_no_repository_mutation(repo):
    def fingerprint():
        return {str(p.relative_to(repo)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in repo.rglob('*') if p.is_file()}
    before = fingerprint()
    assert run(repo) == run(repo)
    assert before == fingerprint()


@pytest.mark.parametrize('field', [
    'status', 'reasoning_change_status', 'reasoning_change_report_sha256',
    'graph_store_head_sha256', 'before_snapshot_sha256', 'after_snapshot_sha256',
    'document_sha256', 'bindings_sha256', 'explicit_binding_count',
    'reasoning_event_count', 'section_review_count', 'section_review_tasks',
    'unmapped_inference_events', 'authority',
])
def test_independent_verifier_rejects_edited_report_even_if_rehashed(repo, field):
    from audit_engine.semantic_audit.graph.persistent_domain_state import canonical, sha
    result = run(repo)
    if field == 'section_review_tasks':
        result[field][0]['triggers'][0]['event_kind'] = 'added' if result[field][0]['triggers'][0]['event_kind'] != 'added' else 'retracted'
    elif field == 'unmapped_inference_events':
        result[field].append({'event_kind': 'forged'})
    elif field == 'authority':
        result[field]['automatic_approval_permitted'] = True
    elif type(result[field]) is int:
        result[field] += 1
    else:
        result[field] = 'altered'
    result['report_sha256'] = sha(canonical({k:v for k,v in result.items() if k != 'report_sha256'}))
    with pytest.raises(G73Error, match='mismatch'):
        verify(repo, result, document_path=DOCUMENT, bindings_path=BINDINGS,
               mode='candidate', knowledge_graph=CANDIDATE)


def test_mapping_missing_is_blocked_not_guessed(repo):
    edit(repo, lambda v: v.update(links=[]))
    result = run(repo)
    assert result['status'] == 'blocked_no_explicit_inference_mapping'
    assert result['section_review_count'] == 0
    assert len(result['unmapped_inference_events']) == 2


def test_partial_mapping_never_declared_complete(repo):
    edit(repo, lambda v: v.update(links=v['links'][:1]))
    result = run(repo)
    assert result['status'] == 'partial_inference_mapping_requires_review'
    assert result['section_review_count'] == 1
    assert len(result['unmapped_inference_events']) == 1


def test_both_changed_facts_may_map_to_one_section(repo):
    def rewrite(v):v['links'][1]['section_id'] = v['links'][0]['section_id']
    edit(repo, rewrite)
    result = run(repo)
    assert result['status'] == 'human_review_plan_ready'
    assert result['section_review_count'] == 1
    assert len(result['section_review_tasks'][0]['triggers']) == 2


def test_no_prior_transition_produces_no_review_not_fabricated(repo):
    edit(repo, lambda v: v.update(links=[]))
    change = reasoning_change(repo, mode='latest-transition')
    def rebind(v):
        v['expected_before_snapshot_sha256'] = change['before_snapshot_sha256']
        v['expected_after_snapshot_sha256'] = change['after_snapshot_sha256']
    edit(repo, rebind)
    result = run(repo, mode='latest-transition', knowledge_graph=None)
    assert result['reasoning_change_status'] == 'no_prior_transition'
    assert result['status'] == 'no_inference_change'
    assert result['section_review_count'] == 0
    assert not result['unmapped_inference_events']


@pytest.mark.parametrize('field', [
    'document_id', 'document_sha256', 'expected_store_head_sha256',
    'expected_before_snapshot_sha256', 'expected_after_snapshot_sha256',
    'schema_version',
])
def test_stale_binding_or_invalid_schema_rejected(repo, field):
    edit(repo, lambda v: v.update({field: 'x' * 64}))
    with pytest.raises((G73Error, GE04Error)):
        run(repo)


def test_changed_document_rejected(repo):
    path = repo / DOCUMENT
    path.write_text(path.read_text().replace('FEM assumptions', 'ADJUSTED FEM assumptions'))
    with pytest.raises(G73Error, match='Stale binding'):
        run(repo)


def test_changed_candidate_rejected(repo):
    path = repo / CANDIDATE
    raw = json.loads(path.read_text())
    next(iter(raw['concepts'].values()))['name'] += ' Changed'
    path.write_text(json.dumps(raw))
    with pytest.raises((G73Error, ValueError)):
        run(repo)


def test_dangling_inference_rejected(repo):
    edit(repo, lambda v: v['links'][0]['fact'].update(target_id='invented:target'))
    with pytest.raises(G73Error, match='absent or unchanged'):
        run(repo)


def test_dangling_section_rejected(repo):
    edit(repo, lambda v: v['links'][0].update(section_id='10000000-0000-0000-0000-000000000099'))
    with pytest.raises(G73Error, match='Dangling section'):
        run(repo)


def test_unauthorized_link_relation_rejected(repo):
    edit(repo, lambda v: v['links'][0].update(relation='AUTOMATICALLY_APPROVES'))
    with pytest.raises(G73Error, match='explicitly review'):
        run(repo)


def test_duplicate_section_fact_rejected(repo):
    edit(repo, lambda v: v['links'].append(copy.deepcopy(v['links'][0])))
    with pytest.raises(G73Error, match='Duplicate'):
        run(repo)


def test_duplicate_json_keys_rejected(repo):
    (repo / BINDINGS).write_text('{"schema_version": 1, "schema_version": 2}')
    with pytest.raises((GE04Error, G73Error, GraphStoreError)):
        run(repo)


def test_malformed_document_or_section_rejected_even_when_rehashed(repo):
    path = repo / DOCUMENT
    doc = json.loads(path.read_text());doc['children'][1]['section_id'] = doc['children'][0]['section_id']
    path.write_text(json.dumps(doc));refresh(repo)
    with pytest.raises(GE04Error, match='Duplicate'):
        run(repo)


def test_corrupt_persisted_state_fails_before_review(repo):
    head = repo / '.graph-state/scientific/HEAD.json'
    head.write_text('not JSON')
    with pytest.raises((G72Error, GraphStoreError, ValueError, KeyError)):
        run(repo)


def test_symlink_input_rejected(repo):
    path=repo / BINDINGS
    outside=repo.parent / 'external-bindings.json'
    outside.write_bytes(path.read_bytes());path.unlink();path.symlink_to(outside)
    with pytest.raises((GE04Error, G73Error)):
        run(repo)


def test_traversal_document_rejected(repo):
    with pytest.raises((GE04Error, G73Error)):
        run(repo, document_path='../invalid.json')


def test_rewitnessed_event_retains_before_and_after_proofs():
    from audit_engine.semantic_audit.graph.persistent_domain_state import canonical, sha
    fact={'rule_id':'R','source_id':'X','inferred_relation':'A','target_id':'Y'}
    before=dict(fact,path_node_ids=['X','Y'])
    after=dict(fact,path_node_ids=['X','Z','Y'])
    rows=_event_rows({'added_inferences':[],'retracted_inferences':[],
                      'rewitnessed_inferences':[{'fact': fact,'before':before,'after':after}]})
    assert rows[0]['event_kind'] == 'rewitnessed'
    assert rows[0]['before_witness_sha256'] == sha(canonical(before))
    assert rows[0]['after_witness_sha256'] == sha(canonical(after))
    assert rows[0]['before_witness_sha256'] != rows[0]['after_witness_sha256']


def test_rewitnessed_mismatched_identity_rejected():
    f={'rule_id':'R','source_id':'X','inferred_relation':'A','target_id':'Y'}
    with pytest.raises(G73Error, match='identity mismatch'):
        _event_rows({'added_inferences':[],'retracted_inferences':[],
                     'rewitnessed_inferences':[{'fact':f,'before':f,'after':{**f,'target_id':'Z'}}]})


def test_invalid_report_shapes_rejected(repo):
    for candidate in ([], None, False, 'hello'):
        with pytest.raises(G73Error):
            verify(repo, candidate, document_path=DOCUMENT, bindings_path=BINDINGS,
                   mode='candidate', knowledge_graph=CANDIDATE)
