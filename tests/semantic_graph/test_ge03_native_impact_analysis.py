"""GE-03 contract tests against actual GE-01, GE-02, and native graph evolution APIs."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import uuid

import pytest

from audit_engine.semantic_audit.graph.domain_integration import from_scientific_graph
from audit_engine.semantic_audit.graph.persistent_domain_state import (
    PersistentDomainGraphStore, GraphStoreError, canonical,
)
from audit_engine.semantic_audit.graph.native_impact_analysis import (
    GE03Error, analyze, main, _write_report, SCHEMA,
)

REPO = Path(__file__).resolve().parents[2]
A, B, P = (str(uuid.UUID(int=i)) for i in (1, 2, 3))
ID_A = f'scientific:concept:{A}'
ID_B = f'scientific:concept:{B}'
ID_P = f'scientific:proposition:{P}'


def source_graph():
    return json.loads((REPO/'examples/graph_engine/ge02_demo_graph.json').read_text())


def changed_graph():
    graph = source_graph()
    graph['concepts'][A]['name'] = 'A justified modification, not verified scientific truth'
    return graph


@pytest.fixture
def src(tmp_path):
    repo = tmp_path/'source'
    (repo/'.graph-state').mkdir(parents=True)
    (repo/'examples').mkdir()
    for name, graph in [('before',source_graph()),('changed',changed_graph())]:
        (repo/'examples'/f'{name}.json').write_text(json.dumps(graph))
    store=PersistentDomainGraphStore(repo/'.graph-state/scientific')
    store.publish(from_scientific_graph(source_graph()),expected_head=None)
    return repo


def test_persisted_baseline_is_verified(src):
    report=analyze(src,mode='candidate',knowledge_graph='examples/changed.json')
    state=PersistentDomainGraphStore(src/'.graph-state/scientific').verify()
    assert report['store_head_sha256']==state['head']
    assert state['generation']==1
    assert report['schema_version']==SCHEMA
    assert report['provenance_verified'] is True


def test_change_propagates_through_native_reverse_relations(src):
    report=analyze(src,mode='candidate',knowledge_graph='examples/changed.json')
    candidates={v['node_id']:v for v in report['review_candidates']}
    assert list(sorted(candidates))==sorted([ID_A,ID_B,ID_P])
    assert candidates[ID_A]['distance']==0
    assert candidates[ID_B]['distance']==1
    assert candidates[ID_P]['distance']==2
    assert report['direct_changes']['modified_nodes']==[ID_A]
    assert report['review_candidate_count']==3
    assert report['status']=='review_candidates_only'


def test_candidate_is_read_only_and_preserves_head(src):
    before=PersistentDomainGraphStore(src/'.graph-state/scientific').verify()
    _=analyze(src,mode='candidate',knowledge_graph='examples/changed.json')
    after=PersistentDomainGraphStore(src/'.graph-state/scientific').verify()
    assert after==before
    assert not (src/'.graph-state/scientific/.publication.lock').exists()


def test_noop_has_no_impacted_nodes(src):
    report=analyze(src,mode='candidate',knowledge_graph='examples/before.json')
    assert report['status']=='no_structural_change'
    assert report['delta_is_noop'] is True
    assert report['review_candidate_count']==0
    assert report['direct_changes']['modified_nodes']==[]


def test_baseline_single_generation_is_not_a_historical_change(src):
    report=analyze(src,mode='latest-transition')
    assert report['status']=='no_prior_transition'
    assert report['delta_id'] is None
    assert report['review_candidates']==[]
    assert report['review_candidate_count']==0


def test_committed_history_transition_verified_and_reused(src):
    store=PersistentDomainGraphStore(src/'.graph-state/scientific')
    first=store.verify()
    store.publish(from_scientific_graph(changed_graph()),expected_head=first['head'])
    report=analyze(src,mode='latest-transition')
    assert report['store_generation']==2
    assert {item['node_id'] for item in report['review_candidates']}=={ID_A,ID_B,ID_P}
    assert report['direct_changes']['modified_nodes']==[ID_A]
    assert report['compared_snapshot_sha256']==store.verify()['snapshot_sha256']
    assert report['baseline_snapshot_sha256']!=report['compared_snapshot_sha256']


def test_latest_transition_rejects_candidate_path(src):
    with pytest.raises(GE03Error,match='not valid'):
        analyze(src,mode='latest-transition',knowledge_graph='examples/before.json')


def test_missing_baseline_fails_closed(tmp_path):
    repo=tmp_path/'empty';repo.mkdir()
    with pytest.raises((GraphStoreError,GE03Error)):
        analyze(repo,mode='latest-transition')


def test_corrupted_head_fails_closed(src):
    head=src/'.graph-state/scientific/HEAD.json'
    data=json.loads(head.read_text());data['head_sha256']='0'*64
    head.write_text(json.dumps(data))
    with pytest.raises(GraphStoreError):
        analyze(src,mode='latest-transition')


def test_corrupted_committed_object_fails_closed(src):
    store=PersistentDomainGraphStore(src/'.graph-state/scientific')
    state=store.verify();receipt=store._cas_read('commits',state['head'])
    p=store.root/'objects'/(receipt['snapshot_object_sha256']+'.json')
    p.write_bytes(p.read_bytes()+b' ')
    with pytest.raises(GraphStoreError):
        analyze(src,mode='candidate',knowledge_graph='examples/changed.json')


def test_corrupted_historical_transition_fails_closed(src):
    store=PersistentDomainGraphStore(src/'.graph-state/scientific')
    store.publish(from_scientific_graph(changed_graph()),expected_head=store.verify()['head'])
    current=store._cas_read('commits',store.verify()['head'])
    f=store.root/'transitions'/(current['transition_object_sha256']+'.json')
    f.write_text('{}')
    with pytest.raises(GraphStoreError):
        analyze(src,mode='latest-transition')


def test_symlink_candidate_rejected(src,tmp_path):
    target=tmp_path/'external.json';target.write_text(json.dumps(changed_graph()))
    (src/'examples/linked.json').symlink_to(target)
    with pytest.raises(GE03Error,match='unsafe'):
        analyze(src,mode='candidate',knowledge_graph='examples/linked.json')


def test_traversal_candidate_rejected(src):
    with pytest.raises(GE03Error,match='unsafe'):
        analyze(src,mode='candidate',knowledge_graph='../outside.json')


def test_symlink_store_rejected(src,tmp_path):
    (src/'.graph-state/scientific_symlink').symlink_to(src/'.graph-state/scientific',target_is_directory=True)
    with pytest.raises(GE03Error,match='Symlink'):
        analyze(src,mode='latest-transition',store='.graph-state/scientific_symlink')


def test_bad_store_scope_rejected(src):
    with pytest.raises(GE03Error,match='Store'):
        analyze(src,mode='latest-transition',store='../../tmp')


def test_missing_candidate_rejected(src):
    with pytest.raises(GE03Error,match='requires'):
        analyze(src,mode='candidate')


def test_foreign_domain_cannot_be_inferred(src):
    with pytest.raises(GE03Error):
        analyze(src,mode='invalid',knowledge_graph='examples/changed.json')


def test_malformed_scientific_graph_rejected(src):
    (src/'examples/malformed.json').write_text('{')
    with pytest.raises(GE03Error,match='unsafe'):
        analyze(src,mode='candidate',knowledge_graph='examples/malformed.json')


def test_dangling_scientific_reference_rejected(src):
    data=changed_graph()
    data['propositions'][P]['concept_ids'].append(str(uuid.uuid4()))
    (src/'examples/dangling.json').write_text(json.dumps(data))
    with pytest.raises(GE03Error,match='unsafe'):
        analyze(src,mode='candidate',knowledge_graph='examples/dangling.json')


def test_negative_authority_contract(src):
    report=analyze(src,mode='candidate',knowledge_graph='examples/changed.json')
    assert report['scientific_truth_established'] is False
    assert report['automatic_approval_permitted'] is False
    assert report['authoritative_graph_mutation_permitted'] is False
    assert report['document_section_mapping_available'] is False
    assert report['unmapped_document_section_ids']==[]


def test_deterministic_report_without_timestamp(src):
    a=analyze(src,mode='candidate',knowledge_graph='examples/changed.json')
    b=analyze(src,mode='candidate',knowledge_graph='examples/changed.json')
    assert a == b
    assert a['report_sha256']==__import__('hashlib').sha256(canonical({k:v for k,v in a.items() if k!='report_sha256'})).hexdigest()


def test_no_clobber_report(src,tmp_path):
    output=tmp_path/'report.json';report=analyze(src,mode='latest-transition')
    _write_report(output,report)
    with pytest.raises(GE03Error,match='existing'):
        _write_report(output,report)


def test_symlink_report_rejected(src,tmp_path):
    external=tmp_path/'existing';external.write_text('unchanged')
    link=tmp_path/'link';link.symlink_to(external)
    with pytest.raises(GE03Error,match='Symlink'):
        _write_report(link,analyze(src,mode='latest-transition'))
    assert external.read_text()=='unchanged'


def test_cli_writes_verified_report_outside_repository(src,tmp_path):
    output=tmp_path/'reports/out.json'
    assert main(['--repository',str(src),'--mode','candidate','--knowledge-graph','examples/changed.json','--output',str(output)])==0
    data=json.loads(output.read_text())
    assert data['report_sha256']==analyze(src,mode='candidate',knowledge_graph='examples/changed.json')['report_sha256']


def test_cli_refuses_report_inside_repository(src):
    with pytest.raises(GE03Error,match='outside'):
        main(['--repository',str(src),'--mode','latest-transition','--output',str(src/'report.json')])


def test_existing_nodes_without_dependencies_not_marked(src):
    graph=source_graph()
    D=str(uuid.UUID(int=44))
    graph['concepts'][D]={'concept_id':D,'name':'Unconnected concept','type':'concept','source_ids':[], 'parent_concept_ids':[]}
    (src/'examples/unrelated.json').write_text(json.dumps(graph))
    report=analyze(src,mode='candidate',knowledge_graph='examples/unrelated.json')
    assert {x['node_id'] for x in report['review_candidates']}=={f'scientific:concept:{D}'}
    assert report['review_candidate_count']==1


def test_transition_detects_edge_addition(src):
    graph=source_graph()
    # Reparent B: remove existing edge and introduce edge from newly created concept D.
    D=str(uuid.UUID(int=44))
    graph['concepts'][D]={'concept_id':D,'name':'Independent concept','type':'concept','source_ids':[], 'parent_concept_ids':[]}
    graph['concepts'][B]['parent_concept_ids']=[D]
    (src/'examples/reparent.json').write_text(json.dumps(graph))
    report=analyze(src,mode='candidate',knowledge_graph='examples/reparent.json')
    assert report['direct_changes']['added_edges']
    assert report['direct_changes']['removed_edges']
    assert ID_P in {n['node_id'] for n in report['review_candidates']}
