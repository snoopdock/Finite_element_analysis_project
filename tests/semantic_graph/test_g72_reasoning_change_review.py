"""G7.2 end-to-end reasoning lifecycle, evidence, history and tamper tests."""
import copy
import json
import shutil
from pathlib import Path

import pytest

from audit_engine.semantic_audit.core.semantic_graph import SemanticNode, SemanticEdge, SemanticGraph
from audit_engine.semantic_audit.graph.domain_integration import GraphDomainView, from_scientific_graph
from audit_engine.semantic_audit.graph.persistent_domain_state import (
    PersistentDomainGraphStore, GraphStoreError, sha, canonical,
)
from audit_engine.semantic_audit.graph import reasoning_change_review as r


def view(*, relations=(('A','B'),('B','C')), prop=True, metadata='original', extra=()):
    g=SemanticGraph()
    for node in ('A','B','C','D'):
        g.add_node(SemanticNode(node,'ScientificConcept'))
    g.add_node(SemanticNode('P','ScientificProposition'))
    for s,t in relations:
        g.add_edge(SemanticEdge(s,t,'SUBCONCEPT_OF',metadata={'marker':metadata}))
    if prop:
        g.add_edge(SemanticEdge('P','A','HAS_CONCEPT'))
    for s,t,kind in extra:
        g.add_edge(SemanticEdge(s,t,kind))
    return GraphDomainView(g,'scientific_knowledge','9'*64)


def review(a,b):
    return r.review_views(a,b,mode='candidate',head_sha256='a'*64,store_generation=1)


def record_ids(items):
    return {(x['rule_id'],x['source_id'],x['target_id']) for x in items}


def test_direct_edge_removal_retracts_transitive_and_proposition_facts():
    x=review(view(),view(relations=(('A','B'),)))
    assert x['status']=='inference_review_required'
    assert ('G7.R1.SUBCONCEPT_TRANSITIVE','A','C') in record_ids(x['retracted_inferences'])
    assert ('G7.R2.PROPOSITION_ANCESTOR_ASSOCIATION','P','C') in record_ids(x['retracted_inferences'])
    assert x['added_inferences']==[]
    assert x['before_inference_count']==3
    assert x['after_inference_count']==1
    assert x['unchanged_inference_count']==1
    assert x['structural_review_candidate_count']>=2


def test_edge_addition_creates_facts():
    x=review(view(relations=(('A','B'),)),view())
    assert len(x['added_inferences'])==2
    assert x['retracted_inferences']==[]


def test_reparenting_both_adds_and_retracts():
    x=review(view(),view(relations=(('A','B'),('B','D'))))
    assert len(x['added_inferences'])==2
    assert len(x['retracted_inferences'])==2
    assert x['unchanged_inference_count']==1


def test_witness_metadata_change_preserves_fact_but_updates_proof():
    x=review(view(),view(metadata='revised'))
    assert not x['added_inferences'] and not x['retracted_inferences']
    assert len(x['rewitnessed_inferences'])==3
    w=x['rewitnessed_inferences'][0]
    assert w['before']['path_node_ids']==w['after']['path_node_ids']
    assert w['before']['supporting_edge_sha256s'] != w['after']['supporting_edge_sha256s']


def test_adding_unrelated_node_leaves_facts_unchanged():
    before=view();after=view()
    after.graph.add_node(SemanticNode('Unrelated','ScientificConcept'))
    x=review(before,after)
    assert x['status']=='graph_changed_inferences_unchanged'
    assert x['unchanged_inference_count']==3
    assert not x['added_inferences'] and not x['retracted_inferences'] and not x['rewitnessed_inferences']


def test_non_reasoning_edges_do_not_create_new_inferences():
    x=review(view(),view(extra=(('P','B','CITES_SOURCE'),)))
    assert x['status']=='graph_changed_inferences_unchanged'
    assert x['unchanged_inference_count']==3


def test_noop_has_no_changes():
    a=view();b=view()
    x=review(a,b)
    assert x['status']=='no_structural_change'
    assert x['native_graph_delta_is_noop'] is True
    assert x['structural_review_candidates']==[]
    assert x['before_reasoning_sha256']==x['after_reasoning_sha256']


def test_equal_semantics_different_insertion_order_still_noop():
    a=view();b=view()
    b.graph.edges.reverse();b.graph.nodes.reverse()
    x=review(a,b)
    assert x['status']=='no_structural_change'


def test_rule_replay_has_full_edge_witnesses():
    x=review(view(relations=(('A','B'),)),view())
    for fact in x['added_inferences']:
        assert len(fact['supporting_edge_sha256s'])==len(fact['path_node_ids'])-1
        assert all(len(k)==64 for k in fact['supporting_edge_sha256s'])


def test_authority_explicitly_non_authoritative():
    x=review(view(),view())
    assert all(value is False for value in x['authority'].values())
    assert x['domain']=='scientific_knowledge'


def test_reject_wrong_graph_domain():
    v=view();bad=GraphDomainView(v.graph,'generated_text_audit',v.input_sha256)
    with pytest.raises(r.G72Error,match='scientific_knowledge'):
        review(v,bad)


def test_reject_invalid_reparent_cycle():
    with pytest.raises(r.G7ReasoningError,match='Cyclic'):
        review(view(),view(relations=(('A','B'),('B','C'),('C','A'))))


def test_reject_incorrect_relation_endpoint_types():
    bad=view();bad.graph.add_edge(SemanticEdge('P','A','SUBCONCEPT_OF'))
    with pytest.raises(r.G7ReasoningError,match='concept-to-concept'):
        review(view(),bad)


def test_reject_cross_mode_or_untrusted_head():
    with pytest.raises(r.G72Error,match='mode'):
        r.review_views(view(),view(),mode='invalid',head_sha256='a'*64,store_generation=1)
    with pytest.raises(r.G72Error,match='HEAD'):
        r.review_views(view(),view(),mode='candidate',head_sha256='garbage',store_generation=1)


def test_reject_false_persisted_transition():
    with pytest.raises(r.G72Error,match='disagree'):
        r.review_views(view(),view(),mode='candidate',head_sha256='a'*64,
                       store_generation=1,persisted_transition={'fake':'transition'})


def test_reject_false_claim_of_historical_predecessor():
    with pytest.raises(r.G72Error,match='predecessor'):
        r.review_views(view(),view(metadata='changed'),mode='latest-transition',
                       head_sha256='a'*64,store_generation=1)


def test_no_prior_transition_returns_empty_review():
    x=r.review_views(view(),view(),mode='latest-transition',head_sha256='a'*64,
                     store_generation=1)
    assert x['status']=='no_prior_transition'
    assert x['retracted_inferences']==[]
    assert x['added_inferences']==[]


@pytest.fixture
def repo(tmp_path):
    source=Path(__file__).resolve().parents[2]
    target=tmp_path/'repo'
    target.mkdir()
    shutil.copytree(source/'.graph-state/scientific',target/'.graph-state/scientific')
    (target/'examples').mkdir()
    shutil.copy2(source/'examples/graph_engine/ge02_demo_graph.json',target/'examples/original.json')
    shutil.copy2(source/'examples/graph_engine/g72_demo_reparented_graph.json',target/'examples/candidate.json')
    return target


def test_end_to_end_candidate_reparenting(repo):
    result=r.analyze(repo,mode='candidate',knowledge_graph='examples/candidate.json')
    assert result['status']=='inference_review_required'
    assert len(result['added_inferences'])==1
    assert len(result['retracted_inferences'])==1
    assert result['verified_store_generation']==1
    assert r.verify(repo,result,mode='candidate',knowledge_graph='examples/candidate.json')['status']=='verified'


def test_end_to_end_noop_fixture(repo):
    result=r.analyze(repo,mode='candidate',knowledge_graph='examples/original.json')
    assert result['status']=='no_structural_change'


def test_latest_transition_without_history(repo):
    result=r.analyze(repo,mode='latest-transition')
    assert result['status']=='no_prior_transition'
    assert result['before_inference_count']==result['after_inference_count']


def test_end_to_end_two_generation_transition(repo):
    store=PersistentDomainGraphStore(repo/'.graph-state/scientific')
    candidate=from_scientific_graph(json.loads((repo/'examples/candidate.json').read_text()))
    state=store.verify()
    pub=store.publish(candidate,expected_head=state['head'])
    assert pub['generation']==2
    result=r.analyze(repo,mode='latest-transition')
    assert result['status']=='inference_review_required'
    assert len(result['retracted_inferences'])==1
    assert len(result['added_inferences'])==1
    assert result['historical_parent_commit_sha256']==state['head']
    assert r.verify(repo,result,mode='latest-transition')['status']=='verified'


def test_rehashed_forged_retraction_rejected(repo):
    report=r.analyze(repo,mode='candidate',knowledge_graph='examples/candidate.json')
    report['retracted_inferences'][0]['target_id']='forged'
    report['report_sha256']=sha(canonical({k:v for k,v in report.items() if k!='report_sha256'}))
    with pytest.raises(r.G72Error,match='mismatch'):
        r.verify(repo,report,mode='candidate',knowledge_graph='examples/candidate.json')


def test_rehashed_forged_witness_rejected(repo):
    report=r.analyze(repo,mode='candidate',knowledge_graph='examples/candidate.json')
    report['added_inferences'][0]['supporting_edge_sha256s'][0]='1'*64
    report['report_sha256']=sha(canonical({k:v for k,v in report.items() if k!='report_sha256'}))
    with pytest.raises(r.G72Error,match='mismatch'):
        r.verify(repo,report,mode='candidate',knowledge_graph='examples/candidate.json')


@pytest.mark.parametrize('field',[
    'automatic_approval_permitted','scientific_truth_established',
    'authoritative_graph_mutation_permitted','automatic_document_edits_permitted'
])
def test_rehashed_authority_forgery_rejected(repo,field):
    report=r.analyze(repo,mode='candidate',knowledge_graph='examples/candidate.json')
    report['authority'][field]=True
    report['report_sha256']=sha(canonical({k:v for k,v in report.items() if k!='report_sha256'}))
    with pytest.raises(r.G72Error,match='mismatch'):
        r.verify(repo,report,mode='candidate',knowledge_graph='examples/candidate.json')


def test_rehashed_graph_delta_id_forgery_rejected(repo):
    report=r.analyze(repo,mode='candidate',knowledge_graph='examples/candidate.json')
    report['native_graph_delta_id']='0'*64
    report['report_sha256']=sha(canonical({k:v for k,v in report.items() if k!='report_sha256'}))
    with pytest.raises(r.G72Error,match='mismatch'):
        r.verify(repo,report,mode='candidate',knowledge_graph='examples/candidate.json')


def test_candidate_source_changes_invalidate_report(repo):
    report=r.analyze(repo,mode='candidate',knowledge_graph='examples/candidate.json')
    p=repo/'examples/candidate.json'
    contents=json.loads(p.read_text());c=next(iter(contents['concepts'].values()));c['name']='Changed after report'
    p.write_text(json.dumps(contents))
    with pytest.raises(r.G72Error,match='mismatch'):
        r.verify(repo,report,mode='candidate',knowledge_graph='examples/candidate.json')


def test_reject_invalid_store(repo):
    with pytest.raises(r.G72Error,match='Store'):
        r.analyze(repo,mode='latest-transition',store='../outside')


def test_reject_missing_candidate(repo):
    with pytest.raises(r.G72Error,match='requires'):
        r.analyze(repo,mode='candidate')


def test_reject_graph_arg_in_historical_mode(repo):
    with pytest.raises(r.G72Error,match='forbids'):
        r.analyze(repo,mode='latest-transition',knowledge_graph='examples/candidate.json')


def test_reject_corrupted_persisted_head(repo):
    p=repo/'.graph-state/scientific/HEAD.json'
    p.write_text(p.read_text().replace('"head_sha256"','"bad_hash"'))
    with pytest.raises(GraphStoreError):
        r.analyze(repo,mode='latest-transition')


def test_reject_symlink_graph_source(repo):
    (repo/'examples/symlink.json').symlink_to(repo/'examples/candidate.json')
    with pytest.raises(GraphStoreError):
        r.analyze(repo,mode='candidate',knowledge_graph='examples/symlink.json')


def test_report_exclusive_publication(tmp_path):
    out=tmp_path/'review.json'
    r._write_new(out, review(view(),view()))
    assert r._read_bounded_json(out)['status']=='no_structural_change'
    with pytest.raises(FileExistsError):
        r._write_new(out, review(view(),view()))


def test_no_repository_mutation(repo):
    source=repo/'.graph-state/scientific/HEAD.json'
    before=source.read_bytes()
    r.analyze(repo,mode='candidate',knowledge_graph='examples/candidate.json')
    r.analyze(repo,mode='latest-transition')
    assert source.read_bytes()==before


def test_cli_round_trip(repo,tmp_path):
    output=tmp_path/'result.json'
    args=['--repository',str(repo),'--mode','candidate','--knowledge-graph',
          'examples/candidate.json','--report',str(output)]
    assert r.main(['run',*args])==0
    assert r.main(['verify',*args])==0


def test_reject_report_inside_repo(repo):
    with pytest.raises(r.G72Error,match='detached'):
        r.main(['run','--repository',str(repo),'--report',str(repo/'internal.json'),
                '--mode','latest-transition'])
