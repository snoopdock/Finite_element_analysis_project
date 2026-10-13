"""G7.1 source-bound bounded inference and adversarial proof verification."""
import copy
import json
from pathlib import Path
import pytest

from audit_engine.semantic_audit.core.semantic_graph import SemanticNode, SemanticEdge, SemanticGraph
from audit_engine.semantic_audit.graph.domain_integration import GraphDomainView
from audit_engine.semantic_audit.graph.persistent_domain_state import sha, canonical
from audit_engine.semantic_audit.graph import structural_reasoning as r


def view(*, parallel=False, long=False, isolated=False):
    graph = SemanticGraph()
    for name in (['A', 'B', 'C', 'D'] if long else ['A', 'B', 'C']):
        graph.add_node(SemanticNode(name, 'ScientificConcept'))
    graph.add_node(SemanticNode('P', 'ScientificProposition'))
    graph.add_node(SemanticNode('U', 'ScientificSourceRef'))
    graph.add_edge(SemanticEdge('A','B','SUBCONCEPT_OF', metadata={'source':'ab'}))
    graph.add_edge(SemanticEdge('B','C','SUBCONCEPT_OF', metadata={'source':'bc'}))
    if long: graph.add_edge(SemanticEdge('C','D','SUBCONCEPT_OF'))
    graph.add_edge(SemanticEdge('P','A','HAS_CONCEPT'))
    graph.add_edge(SemanticEdge('P','U','CITES_SOURCE'))
    if parallel:
        graph.add_edge(SemanticEdge('A','B','SUBCONCEPT_OF',metadata={'source':'alternate'}))
    if isolated:
        graph.add_edge(SemanticEdge('A','C','SCIENTIFIC_RELATION'))
    return GraphDomainView(graph,'scientific_knowledge','9'*64)


def test_closure_produces_transitive_fact():
    x=r.reason(view())
    assert ('A','C','SUBCONCEPT_OF') in {(i['source_id'],i['target_id'],i['inferred_relation']) for i in x['inferences']}
    assert x['inference_count']==3  # A->C, P->B, P->C
    assert r.verify_reasoning(view(), x)['status']=='verified'


def test_paths_explain_each_edge():
    x=r.reason(view())
    a=next(i for i in x['inferences'] if i['source_id']=='A')
    assert a['path_node_ids']==['A','B','C']
    assert len(a['supporting_edge_sha256s']) == 2
    p=next(i for i in x['inferences'] if i['source_id']=='P' and i['target_id']=='C')
    assert p['path_node_ids']==['P','A','B','C']
    assert len(p['supporting_edge_sha256s']) == 3


def test_shorter_paths_preferred_and_duplicate_suppressed():
    x=r.reason(view(long=True))
    keys=[(i['rule_id'],i['source_id'],i['target_id']) for i in x['inferences']]
    assert len(keys)==len(set(keys))
    assert any(i['path_node_ids']==['A','B','C','D'] for i in x['inferences'])


def test_unchanged_graph_deterministic_with_reordering():
    v=view(parallel=True)
    expected=r.reason(v)
    v.graph.edges.reverse()
    v.graph.nodes.reverse()
    assert r.reason(v)==expected


def test_source_metadata_affects_witness():
    v=view()
    x=r.reason(v)
    v.graph.edges[0].metadata['source']='modified'
    with pytest.raises(r.G7ReasoningError,match='mismatch'):
        r.verify_reasoning(v,x)


def test_unrelated_and_unverified_citations_never_infer():
    x=r.reason(view(isolated=True))
    assert x['inference_count']==3
    assert all(i['rule_id'] in r.RULES for i in x['inferences'])
    assert not x['authority']['scientific_truth_established']


def test_scientific_relation_does_not_generate_closure():
    v=view()
    v.graph.edges=[e for e in v.graph.edges if e.relation_type!='SUBCONCEPT_OF']
    assert r.reason(v)['inference_count']==0


def test_reject_cycle():
    v=view()
    v.graph.add_edge(SemanticEdge('C','A','SUBCONCEPT_OF'))
    with pytest.raises(r.G7ReasoningError,match='Cyclic'):
        r.reason(v)


def test_reject_wrong_hierarchy_types():
    v=view()
    v.graph.add_edge(SemanticEdge('P','B','SUBCONCEPT_OF'))
    with pytest.raises(r.G7ReasoningError,match='concept-to-concept'):
        r.reason(v)


def test_reject_wrong_has_concept_types():
    v=view()
    v.graph.add_edge(SemanticEdge('A','B','HAS_CONCEPT'))
    with pytest.raises(r.G7ReasoningError,match='proposition-to-concept'):
        r.reason(v)


def test_reject_cross_domain():
    v=view();v=GraphDomainView(v.graph,'generated_text_audit',v.input_sha256)
    with pytest.raises(r.G7ReasoningError,match='scientific_knowledge'):
        r.reason(v)


def test_reject_resource_limit(monkeypatch):
    monkeypatch.setattr(r,'MAX_NODES',3)
    with pytest.raises(r.G7ReasoningError,match='budget'):
        r.reason(view())


def test_reject_deep_hierarchy(monkeypatch):
    monkeypatch.setattr(r,'MAX_HOPS',1)
    with pytest.raises(r.G7ReasoningError,match='budget'):
        r.reason(view())


def test_reject_fact_budget(monkeypatch):
    monkeypatch.setattr(r,'MAX_FACTS',2)
    with pytest.raises(r.G7ReasoningError,match='budget'):
        r.reason(view())


@pytest.mark.parametrize('mutation',[
    lambda x: x.update(inference_count=99),
    lambda x: x['inferences'][0].update(target_id='fake'),
    lambda x: x['inferences'][0]['supporting_edge_sha256s'].__setitem__(0,'0'*64),
    lambda x: x['inferences'][0]['path_node_ids'].append('forged'),
    lambda x: x['authority'].update(scientific_truth_established=True),
    lambda x: x['authority'].update(authoritative_graph_mutation_permitted=True),
    lambda x: x.update(source_snapshot_sha256='1'*64),
    lambda x: x.update(unsupported_auto_execute=True),
])
def test_rehashed_forgery_is_rejected(mutation):
    x=copy.deepcopy(r.reason(view()))
    mutation(x)
    x['report_sha256']=sha(canonical({k:v for k,v in x.items() if k!='report_sha256'}))
    with pytest.raises(r.G7ReasoningError,match='mismatch'):
        r.verify_reasoning(view(),x)


def test_duplicate_graph_node_rejected():
    v=view()
    v.graph.nodes.append(SemanticNode('A','ScientificConcept'))
    with pytest.raises(r.G7ReasoningError,match='Duplicate'):
        r.reason(v)


def test_source_snapshot_bound_to_input_digest():
    v=view()
    report=r.reason(v)
    v2=GraphDomainView(v.graph, 'scientific_knowledge', '8'*64)
    with pytest.raises(r.G7ReasoningError,match='mismatch'):
        r.verify_reasoning(v2,report)


def test_persisted_repository_smoke():
    repo=Path(__file__).resolve().parents[2]
    state=repo/'.graph-state/scientific/HEAD.json'
    if not state.exists():
        pytest.skip('Demo persisted GE-02 graph unavailable in exported repository')
    v,head=r._load_view(repo,mode='persisted',knowledge_graph=None,store='.graph-state/scientific')
    result=r.reason(v,store_head=head)
    assert r.verify_reasoning(v,result,store_head=head)['status']=='verified'
    assert result['source_store_head_sha256']==head
    assert result['inference_count']>=1


def test_candidate_fixture_smoke():
    repo=Path(__file__).resolve().parents[2]
    v,head=r._load_view(repo,mode='candidate',knowledge_graph='examples/graph_engine/ge02_demo_graph.json',store='.graph-state/scientific')
    assert head is None
    result=r.reason(v)
    assert result['inference_count']==1
    assert result['inferences'][0]['inferred_relation']=='HAS_ANCESTOR_CONCEPT'


def test_report_exclusive_output(tmp_path):
    p=tmp_path/'sample.json'
    output=r.reason(view())
    r._write_new(p,output)
    assert r._read_bounded_json(p)==output
    with pytest.raises(FileExistsError):
        r._write_new(p,output)


def test_reject_symlink_report(tmp_path):
    p=tmp_path/'real.json';p.write_text('{}')
    link=tmp_path/'alias.json';link.symlink_to(p)
    with pytest.raises(r.G7ReasoningError,match='Symlink'):
        r._read_bounded_json(link)


def test_verify_requires_identical_store_head():
    v=view()
    output=r.reason(v,store_head='1'*64)
    with pytest.raises(r.G7ReasoningError,match='mismatch'):
        r.verify_reasoning(v,output,store_head='2'*64)
