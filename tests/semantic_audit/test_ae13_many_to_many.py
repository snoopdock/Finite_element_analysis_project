import copy
from dataclasses import replace
import pytest
from audit_engine.semantic_audit.graph.analysis import AnalysisType,AnalysisStatus,SemanticContext,SemanticObservation,EvidenceRecord,GraphAnalysisResult,VerificationStatus
from audit_engine.semantic_audit.ae13 import admit_analysis,create_obligation,run_bound_verification
from audit_engine.semantic_audit.ae13.bindings import verify_registry
from audit_engine.semantic_audit.core.semantic_graph import SemanticEdge


def fixture_result():
    a=EvidenceRecord.from_edge(SemanticEdge('one','two','DEPENDS_ON',metadata={'site':'A'}))
    b=EvidenceRecord.from_edge(SemanticEdge('three','four','DEPENDS_ON',metadata={'site':'B'}))
    o1=SemanticObservation.create(subject_id='one',predicate='DEPENDS_ON',object_id='two',evidence_ids=(a.evidence_id,),depth=1)
    o2=SemanticObservation.create(subject_id='three',predicate='DEPENDS_ON',object_id='four',evidence_ids=(b.evidence_id,),depth=1)
    return GraphAnalysisResult(analysis_id='analysis:fixture',query_id='query:fixture',
        analysis_type=AnalysisType.DEPENDENCY,status=AnalysisStatus.COMPLETED,algorithm='test',
        graph_fingerprint='graph:declared',source_entities=('one','three'),
        observations=(o1,o2),evidence=(a,b),semantic_context=SemanticContext())


def test_two_sources_one_obligation_all():
    r=fixture_result();reg=admit_analysis(r)
    p=create_obligation(r,reg,selected_observations=tuple(o.observation_id for o in r.observations))
    res=run_bound_verification(r,reg,p)
    assert res['decision']=='confirmed_within_declared_graph_contract'
    assert len(res['receipts'])==2 and len(set(x['receipt_id'] for x in res['receipts']))==2


def test_one_source_multiple_independent_obligations():
    r=fixture_result();reg=admit_analysis(r); oid=r.observations[0].observation_id
    p1=create_obligation(r,reg,selected_observations=(oid,))
    p2=create_obligation(r,reg,selected_observations=(oid,r.observations[1].observation_id))
    assert p1['plan_id']!=p2['plan_id']
    assert len(run_bound_verification(r,reg,p1)['receipts'])==1
    assert len(run_bound_verification(r,reg,p2)['receipts'])==2


def test_invalid_pair_rejected_even_if_both_ids_are_in_same_analysis():
    r=fixture_result();reg=admit_analysis(r)
    p=create_obligation(r,reg,selected_observations=(r.observations[0].observation_id,))
    forged=copy.deepcopy(p)
    forged['entries'][0]['witness_links'][0]['evidence_id']=r.evidence[1].evidence_id
    from audit_engine.semantic_audit.ae13.identity import content_id
    forged['plan_id']=content_id('association-plan',{k:v for k,v in forged.items() if k!='plan_id'})
    with pytest.raises(ValueError):run_bound_verification(r,reg,forged)


def test_unknown_evidence_rejected():
    r=fixture_result();bad=replace(r,observations=(replace(r.observations[0],evidence_ids=('other-id',)),))
    with pytest.raises(ValueError):admit_analysis(bad)


def test_duplicate_evidence_identity_rejected():
    r=fixture_result();bad=replace(r,evidence=(r.evidence[0],r.evidence[0]))
    with pytest.raises(ValueError):admit_analysis(bad)


def test_stale_registry_after_changed_source_observation():
    r=fixture_result();reg=admit_analysis(r)
    changed=replace(r,observations=(replace(r.observations[0],object_id='changed'),r.observations[1]))
    with pytest.raises(ValueError): verify_registry(reg,changed)


def test_shared_evidence_across_observations_supported():
    r=fixture_result();shared=replace(r.observations[1],subject_id='one',predicate='DEPENDS_ON',object_id='two',evidence_ids=(r.evidence[0].evidence_id,))
    b=replace(r,observations=(r.observations[0],shared))
    reg=admit_analysis(b)
    p=create_obligation(b,reg,selected_observations=tuple(o.observation_id for o in b.observations))
    assert len(reg['links'])==2
    assert run_bound_verification(b,reg,p)['decision']=='confirmed_within_declared_graph_contract'


def test_unlinked_observations_cannot_be_promoted():
    r=fixture_result();unlinked=replace(r.observations[0],evidence_ids=())
    b=replace(r,observations=(unlinked,r.observations[1]))
    reg=admit_analysis(b)
    assert len(reg['unlinked_observation_ids'])==1
    with pytest.raises(ValueError):create_obligation(b,reg,selected_observations=(unlinked.observation_id,))


def test_plan_quantifier_is_explicit_and_deterministic():
    r=fixture_result();reg=admit_analysis(r);ids=tuple(o.observation_id for o in r.observations)
    a=create_obligation(r,reg,selected_observations=ids,quantifier='any')
    b=create_obligation(r,reg,selected_observations=ids,quantifier='all')
    assert a['plan_id']!=b['plan_id']
    assert a==create_obligation(r,reg,selected_observations=ids[::-1],quantifier='any')
    assert run_bound_verification(r,reg,a)['decision']=='confirmed_within_declared_graph_contract'


def test_foreign_analysis_cannot_reuse_plan():
    r=fixture_result();reg=admit_analysis(r);p=create_obligation(r,reg,selected_observations=(r.observations[0].observation_id,))
    altered=replace(r,analysis_id='analysis:other')
    with pytest.raises(ValueError):run_bound_verification(altered,reg,p)


def test_reject_wrong_verifier_and_empty_selection():
    r=fixture_result();reg=admit_analysis(r)
    with pytest.raises(ValueError):create_obligation(r,reg,selected_observations=())
    with pytest.raises(ValueError):create_obligation(r,reg,selected_observations=(r.observations[0].observation_id,),verifier_id='unknown')


def test_direct_edge_cross_binding_rejected_even_if_declared_in_observation():
    r=fixture_result()
    wrong=replace(r.observations[0],evidence_ids=(r.evidence[1].evidence_id,))
    with pytest.raises(ValueError,match='Direct edge witness'):
        admit_analysis(replace(r,observations=(wrong,r.observations[1])))

def test_real_g3_dependency_graph_end_to_end():
    from audit_engine.semantic_audit.core.semantic_graph import SemanticGraph,SemanticNode,SemanticEdge
    from audit_engine.semantic_audit.graph import SemanticGraphAnalysisService
    from audit_engine.semantic_audit.graph.queries import GraphQuery,QueryType
    graph=SemanticGraph()
    for name in ('app','service','db'):
        graph.add_node(SemanticNode(name,'SoftwareModule'))
    graph.add_edge(SemanticEdge('app','service','IMPORTS',metadata={'source_id':'app.py:2'}))
    graph.add_edge(SemanticEdge('service','db','IMPORTS',metadata={'source_id':'service.py:5'}))
    result=SemanticGraphAnalysisService(graph).analyze(GraphQuery('ae13-path',QueryType.DEPENDENCY,['app'],{'max_depth':2}))
    reg=admit_analysis(result,graph=graph)
    plan=create_obligation(result,reg,selected_observations=tuple(o.observation_id for o in result.observations))
    decision=run_bound_verification(result,reg,plan,graph=graph)
    assert len(decision['receipts'])==2
    assert decision['decision']=='confirmed_within_attested_graph_contract'


def test_forged_direct_evidence_id_rejected():
    r=fixture_result()
    from dataclasses import replace
    fake=replace(r.evidence[0],object_id='forged-target')
    with pytest.raises(ValueError,match='Forged direct edge witness identity'):
        admit_analysis(replace(r,evidence=(fake,r.evidence[1])))


def test_untrusted_verifier_override_is_rejected():
    from audit_engine.semantic_audit.verification import VerifierRegistry
    r=fixture_result();reg=admit_analysis(r)
    p=create_obligation(r,reg,selected_observations=(r.observations[0].observation_id,))
    class Impostor:
        from audit_engine.semantic_audit.verification.verifier import VerifierDescriptor
        descriptor=VerifierDescriptor('observation-contract','1.0.0',('observation_contract',))
        def verify(self, obligation, context):
            raise AssertionError('Must not execute untrusted verifier')
    vr=VerifierRegistry();vr.register(Impostor())
    with pytest.raises(ValueError,match='pinned built-in verifier'):
        run_bound_verification(r,reg,p,registry_of_verifiers=vr)


def test_attested_graph_rejects_modified_edges():
    from audit_engine.semantic_audit.core.semantic_graph import SemanticGraph,SemanticNode,SemanticEdge
    from audit_engine.semantic_audit.graph import SemanticGraphAnalysisService
    from audit_engine.semantic_audit.graph.queries import GraphQuery,QueryType
    graph=SemanticGraph()
    for node in ('A','B'):
        graph.add_node(SemanticNode(node,'Module'))
    graph.add_edge(SemanticEdge('A','B','DEPENDS_ON'))
    result=SemanticGraphAnalysisService(graph).analyze(GraphQuery('t',QueryType.DEPENDENCY,['A'],{}))
    registry=admit_analysis(result,graph=graph)
    graph.edges[0].relation_type='OTHER'
    with pytest.raises(ValueError,match='does not match'):
        admit_analysis(result,graph=graph)
    plan=create_obligation(result,registry,selected_observations=tuple(o.observation_id for o in result.observations))
    with pytest.raises(ValueError):run_bound_verification(result,registry,plan,graph=graph)
