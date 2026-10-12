"""GE-02 integration tests: actual GE-01 projections + existing G3 evolution API."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import uuid

import pytest

from audit_engine.semantic_audit.graph.domain_integration import from_scientific_graph
from audit_engine.semantic_audit.graph.persistent_domain_state import (
    GraphStoreError, PersistentDomainGraphStore, canonical, sha, parse,
    _strict_view, _dependency_candidates, _transition, _input_path,
)

A = str(uuid.UUID(int=1))
B = str(uuid.UUID(int=2))
P = str(uuid.UUID(int=3))


def science():
    return {
        'concepts': {
            A: {'concept_id': A, 'name': 'Reference FEM concept', 'type':'concept',
                'source_ids':['ref-1'], 'parent_concept_ids':[]},
            B: {'concept_id': B, 'name': 'Dependent sub-concept', 'type':'concept',
                'source_ids':[], 'parent_concept_ids':[A]},
        },
        'propositions': {P: {'proposition_id': P, 'statement':'Example proposition (not verified)',
                            'concept_ids':[B], 'source_ids':['ref-1'], 'status':'proposed'}},
        'relationships':{},
    }


def view(doc=None):
    return from_scientific_graph(doc or science())


def store(tmp_path):
    return PersistentDomainGraphStore(tmp_path/'store')


def new_version():
    d = science()
    d['concepts'][A]['name'] = 'Updated reference concept'
    return d


def test_ge01_round_trip(tmp_path):
    s=store(tmp_path)
    v=view()
    committed=s.publish(v, expected_head=None)
    assert committed['status']=='verified'
    assert committed['generation']==1
    assert s.current_view().snapshot()==v.snapshot()
    assert committed['domain']=='scientific_knowledge'
    assert committed['commits_verified']==1


def test_repeat_identical_is_idempotent(tmp_path):
    s=store(tmp_path)
    first=s.publish(view(), expected_head=None)
    again=s.publish(view(), expected_head=first['head'])
    assert not again['changed']
    assert again['head']==first['head']
    assert again['generation']==1
    assert len(list((s.root/'objects').glob('*.json')))==1


def test_incremental_diff_uses_existing_evolution_service(tmp_path):
    s=store(tmp_path)
    first=s.publish(view(), expected_head=None)
    updated=s.publish(view(new_version()), expected_head=first['head'])
    t=updated['transition']
    assert updated['generation']==2
    assert not t['graph_delta']['is_noop']
    assert t['schema_version']=='ge02-graph-transition/v1'
    seeds=t['impact']['review_candidates']
    impacts={r['node_id']:r for r in seeds}
    assert f'scientific:concept:{A}' in impacts
    assert f'scientific:concept:{B}' in impacts
    assert f'scientific:proposition:{P}' in impacts
    assert impacts[f'scientific:proposition:{P}']['distance']>=1
    assert t['impact']['automatic_approval_permitted'] is False
    assert s.verify()['commits_verified']==2


def test_previous_history_remains_accessible(tmp_path):
    s=store(tmp_path)
    a=s.publish(view(), expected_head=None)
    b=s.publish(view(new_version()), expected_head=a['head'])
    rec=s._cas_read('commits',b['head'])
    assert rec['parent_receipt_sha256']==a['head']
    assert s._cas_read('commits',a['head'])['generation']==1


def test_existing_lock_fails_closed(tmp_path):
    s=store(tmp_path);s.root.mkdir()
    (s.root/'.publication.lock').write_text('orphan')
    with pytest.raises(GraphStoreError, match='lock'):
        s.publish(view(), expected_head=None)
    assert not (s.root/'HEAD.json').exists()


def test_lock_removed_after_validation_failure(tmp_path):
    s=store(tmp_path);s.publish(view(),expected_head=None)
    with pytest.raises(GraphStoreError,match='Stale'):
        s.publish(view(new_version()),expected_head='0'*64)
    assert not (s.root/'.publication.lock').exists()


def test_expected_head_prevents_lost_update(tmp_path):
    s=store(tmp_path)
    first=s.publish(view(),expected_head=None)
    s.publish(view(new_version()),expected_head=first['head'])
    with pytest.raises(GraphStoreError,match='Stale'):
        s.publish(view(),expected_head=first['head'])
    assert s.verify()['generation']==2


def test_reject_cross_domain(tmp_path):
    s=store(tmp_path)
    first=s.publish(view(),expected_head=None)
    fake=view()
    from audit_engine.semantic_audit.graph.domain_integration import GraphDomainView
    alternate=GraphDomainView(fake.graph,'generated_text_audit',fake.input_sha256)
    with pytest.raises(GraphStoreError,match='Cross-domain'):
        s.publish(alternate,expected_head=first['head'])


def test_reject_modified_object_even_with_unmodified_head(tmp_path):
    s=store(tmp_path)
    first=s.publish(view(),expected_head=None)
    h=s._cas_read('commits',first['head'])['snapshot_object_sha256']
    path=s.root/'objects'/(h+'.json')
    path.write_bytes(path.read_bytes()+b' ') 
    with pytest.raises(GraphStoreError,match='corrupted'):
        s.verify()


def test_reject_corrupted_head(tmp_path):
    s=store(tmp_path);s.publish(view(),expected_head=None)
    f=s.root/'HEAD.json'; d=parse(f.read_bytes());d['head_sha256']='0'*64;f.write_bytes(canonical(d))
    with pytest.raises(GraphStoreError,match='checksum'):
        s.verify()


def test_reject_corrupted_transition(tmp_path):
    s=store(tmp_path)
    first=s.publish(view(), expected_head=None)
    second=s.publish(view(new_version()), expected_head=first['head'])
    key=s._cas_read('commits',second['head'])['transition_object_sha256']
    path=s.root/'transitions'/(key+'.json')
    path.write_text('{}\n')
    with pytest.raises(GraphStoreError, match='corrupted'):
        s.verify()


def test_reject_symlinked_object(tmp_path):
    s=store(tmp_path)
    first=s.publish(view(),expected_head=None)
    key=s._cas_read('commits',first['head'])['snapshot_object_sha256']
    p=s.root/'objects'/(key+'.json');data=p.read_bytes();p.unlink()
    actual=tmp_path/'actual';actual.write_bytes(data);p.symlink_to(actual)
    with pytest.raises(GraphStoreError, match='Symlink'):
        s.verify()


def test_reject_symlinked_store(tmp_path):
    real=tmp_path/'real';real.mkdir()
    link=tmp_path/'link';link.symlink_to(real, target_is_directory=True)
    s=PersistentDomainGraphStore(link)
    with pytest.raises(GraphStoreError,match='Symlink'):
        s.publish(view(),expected_head=None)


def test_graph_snapshots_reject_forged_authority():
    data=view().snapshot()
    data['scientific_truth_established']=True
    with pytest.raises(GraphStoreError,match='authority'):
        _strict_view(data)


def test_graph_snapshots_reject_recomputed_fake_fingerprint():
    data=view().snapshot()
    data['graph']['nodes'][0]['attributes']['name']='forged'
    data['snapshot_sha256']='0'*64
    with pytest.raises(GraphStoreError):_strict_view(data)


def test_no_impact_when_noop():
    v=view()
    t=_transition(v,v)
    assert t['graph_delta']['is_noop']
    assert t['impact']['review_candidates']==[]


def test_unsupported_relation_cannot_imply_dependency():
    x=view()
    v2=copy.deepcopy(x.graph)
    from audit_engine.semantic_audit.core.semantic_graph import SemanticEdge
    v2.add_edge(SemanticEdge(f'scientific:concept:{A}',f'scientific:concept:{B}','SCIENTIFIC_RELATION'))
    from audit_engine.semantic_audit.evolution.service import SemanticGraphEvolutionService
    evolution=SemanticGraphEvolutionService().compare(before_graph=x.graph,after_graph=v2)
    impacts=_dependency_candidates(x.graph,v2,evolution.graph_delta)
    assert impacts['automatic_approval_permitted'] is False
    assert 'SCIENTIFIC_RELATION' not in impacts['dependency_relations']


def test_reject_path_traversal(tmp_path):
    repo=tmp_path/'repo';repo.mkdir()
    with pytest.raises(GraphStoreError):_input_path(repo,'../secrets.json')


def test_reject_symlink_input(tmp_path):
    repo=tmp_path/'repo';repo.mkdir()
    original=repo/'graph.json';original.write_text('{}')
    link=repo/'link.json';link.symlink_to(original)
    with pytest.raises(GraphStoreError):_input_path(repo,'link.json')


def test_cli_capture_verify_and_report(tmp_path):
    repo=tmp_path/'repo';repo.mkdir()
    sample=repo/'science.json';sample.write_text(json.dumps(science()))
    report=tmp_path/'capture-report.json'
    args=[sys.executable,'-m','audit_engine.semantic_audit.graph.persistent_domain_state',
          '--repository',str(repo),'--knowledge-graph','science.json','--report',str(report)]
    root=Path(__file__).resolve().parents[2]
    proc=subprocess.run(args,cwd=root,capture_output=True,text=True,timeout=25)
    assert proc.returncode==0,proc.stderr
    payload=json.loads(proc.stdout)
    assert payload['changed'] and payload['generation']==1
    assert json.loads(report.read_text())['head']==payload['head']
    check=subprocess.run([sys.executable,'-m','audit_engine.semantic_audit.graph.persistent_domain_state',
                          '--repository',str(repo),'--command','verify'],cwd=root,capture_output=True,text=True,timeout=25)
    assert check.returncode==0,check.stderr
    assert json.loads(check.stdout)['generation']==1


def test_cli_reject_source_outside_repo(tmp_path):
    repo=tmp_path/'repo';repo.mkdir()
    with pytest.raises(GraphStoreError): _input_path(repo,'/tmp/graph.json')


def test_snapshot_change_from_content_only_is_reviewed(tmp_path):
    s=store(tmp_path)
    a=s.publish(view(),expected_head=None)
    doc=science();doc['propositions'][P]['statement']='Revised example (still unverified)'
    b=s.publish(view(doc),expected_head=a['head'])
    assert f'scientific:proposition:{P}' in {x['node_id'] for x in b['transition']['impact']['review_candidates']}


def test_verify_empty_store(tmp_path):
    s=store(tmp_path);s.root.mkdir()
    assert s.verify()['status']=='empty'


def test_no_modification_of_knowledge_graph_input(tmp_path):
    doc=science();before=copy.deepcopy(doc)
    s=store(tmp_path);s.publish(from_scientific_graph(doc),expected_head=None)
    assert doc==before


def test_report_no_claim_of_formal_reasoning(tmp_path):
    s=store(tmp_path)
    a=s.publish(view(),expected_head=None)
    result=s.publish(view(new_version()),expected_head=a['head'])
    assert result['transition']['impact']['scientific_truth_established'] is False
    assert result['transition']['impact']['status']=='review_candidates_only'


def test_lock_artifact_not_committed(tmp_path):
    s=store(tmp_path);s.publish(view(),expected_head=None)
    assert not (s.root/'.publication.lock').exists()


def test_invalid_double_key_rejected():
    with pytest.raises(GraphStoreError):parse(b'{"a":1,"a":2}')


def test_nonfinite_rejected():
    with pytest.raises(GraphStoreError):parse(b'{"a":NaN}')
