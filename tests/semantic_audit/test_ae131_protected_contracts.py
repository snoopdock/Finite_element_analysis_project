"""Adversarial controls for protected, backwards-compatible G3 rule admission."""
from dataclasses import replace

import pytest

from audit_engine.semantic_audit.core.semantic_graph import SemanticGraph, SemanticNode, SemanticEdge
from audit_engine.semantic_audit.graph import SemanticGraphAnalysisService
from audit_engine.semantic_audit.graph.queries import GraphQuery, QueryType
from audit_engine.semantic_audit.rules import DomainRuleExecutor, DomainRuleLoader
from audit_engine.semantic_audit.rules.evaluator import RuleEvaluator
from audit_engine.semantic_audit.rules.models import RuleDisposition, SemanticAuditRule, RuleSeverity, RuleEvaluationResult
from audit_engine.semantic_audit.findings.factory import FindingFactory
from audit_engine.semantic_audit.verification import (
    VerificationObligation, VerificationService, VerifierRegistry, ObservationContractVerifier,
    VerificationAttempt, VerificationDecision,
)
from audit_engine.semantic_audit.graph.analysis import VerificationStatus
from audit_engine.semantic_audit.verification.verifier import VerifierDescriptor
from audit_engine.semantic_audit.verification.integrity import validate_receipt_identity


def _data():
    graph=SemanticGraph()
    for x in ('a','b','c'):
        graph.add_node(SemanticNode(x,'Module'))
    graph.add_edge(SemanticEdge('a','b','DEPENDS_ON',metadata={'source_id':'first','ae13_occurrence_id':'first'}))
    graph.add_edge(SemanticEdge('a','c','DEPENDS_ON',metadata={'source_id':'second','ae13_occurrence_id':'second'}))
    result=SemanticGraphAnalysisService(graph).analyze(GraphQuery('q',QueryType.DEPENDENCY,['a'],{'max_depth':1}))
    registry=VerifierRegistry();registry.register(ObservationContractVerifier())
    return graph,result,VerificationService(registry)


def _obligation(result, oid, evidence_ids):
    o=next(o for o in result.observations if o.observation_id==oid)
    return VerificationObligation.from_analysis_result(result,obligation_type='observation_contract',
        observation_ids=[oid],evidence_ids=evidence_ids,requested_verifier_ids=['observation-contract'],
        parameters={'subject_id':o.subject_id,'predicate':o.predicate,'object_id':o.object_id})


def test_actual_cross_observation_evidence_rejected():
    graph,result,service=_data()
    assert len(result.observations)>=2
    x,y=result.observations[:2]
    other=next(e.evidence_ids[0] for e in result.observations if e.observation_id!=x.observation_id)
    with pytest.raises(ValueError,match='unrelated'):
        service.verify(_obligation(result,x.observation_id,[other]),result,semantic_graph=graph)


def test_independent_observation_still_verifies():
    graph,result,service=_data()
    o=next(o for o in result.observations if o.subject_id=='a' and o.object_id=='b')
    receipt=service.verify(_obligation(result,o.observation_id,o.evidence_ids),result,semantic_graph=graph)
    assert receipt.decision is VerificationDecision.CONFIRMED
    assert receipt.evidence_state is VerificationStatus.VALIDATED


def test_one_observation_supports_more_than_one_distinct_plan():
    graph,result,service=_data()
    o=next(o for o in result.observations if o.subject_id=='a')
    x=_obligation(result,o.observation_id,o.evidence_ids)
    y=VerificationObligation.from_analysis_result(result,obligation_type='observation_contract',
       observation_ids=[o.observation_id],evidence_ids=list(o.evidence_ids),
       requested_verifier_ids=['observation-contract'],parameters={'predicate':'DEPENDS_ON'})
    assert x.obligation_id!=y.obligation_id
    assert service.verify(x,result,semantic_graph=graph).decision is VerificationDecision.CONFIRMED
    assert service.verify(y,result,semantic_graph=graph).decision is VerificationDecision.CONFIRMED


def test_multiple_observations_with_exact_union_passes():
    graph,result,service=_data()
    obs=result.observations[:2]
    obligation=VerificationObligation.from_analysis_result(result,obligation_type='observation_contract',
        observation_ids=[o.observation_id for o in obs],
        evidence_ids=sorted({e for o in obs for e in o.evidence_ids}),
        requested_verifier_ids=['observation-contract'],parameters={'predicate':'DEPENDS_ON'})
    assert service.verify(obligation,result,semantic_graph=graph).decision is VerificationDecision.CONFIRMED
    # This particular legacy verifier is existential, NOT an all-observations proof.



def test_unsupported_observation_cannot_be_confirmed_without_witness():
    graph,result,service=_data()
    o=result.observations[0]
    no_witness=replace(o,evidence_ids=())
    mutated=replace(result,observations=(no_witness,)+tuple(result.observations[1:]))
    obligation=_obligation(mutated,o.observation_id,[])
    with pytest.raises(ValueError,match='no supporting evidence'):
        service.verify(obligation,mutated,semantic_graph=graph)


def test_obligation_mutation_rejected():
    _,r,s=_data();o=r.observations[0];original=_obligation(r,o.observation_id,o.evidence_ids)
    changed=replace(original,parameters={'object_id':'c'})
    with pytest.raises(ValueError,match='identity'):
        s.verify(changed,r)


def test_stale_graph_rejected():
    graph,r,s=_data();o=r.observations[0];ob=_obligation(r,o.observation_id,o.evidence_ids)
    graph.nodes[0].attributes['changed']='yes'
    with pytest.raises(ValueError,match='fingerprint'):
        s.verify(ob,r,semantic_graph=graph)


def test_mutated_verifier_graph_after_precheck_rejected():
    graph,r,_=_data();o=r.observations[0];ob=_obligation(r,o.observation_id,o.evidence_ids)
    class MutatingVerifier(ObservationContractVerifier):
        def verify(self,obligation,context):
            result=super().verify(obligation,context)
            graph.nodes[0].attributes['changed']='yes'
            return result
    reg=VerifierRegistry();reg.register(MutatingVerifier())
    with pytest.raises(ValueError,match='changed during'):
        VerificationService(reg).verify(ob,r,semantic_graph=graph)


def test_registered_verifier_cannot_rename_itself_in_attempt():
    _,r,_=_data();o=r.observations[0];ob=_obligation(r,o.observation_id,o.evidence_ids)
    class RenamedVerifier(ObservationContractVerifier):
        def verify(self,obligation,context):
            attempt=super().verify(obligation,context)
            return VerificationAttempt.create(obligation_id=obligation.obligation_id,
                verifier_id='foreign-verifier',verifier_version='999',decision=attempt.decision,
                evidence_state=attempt.evidence_state,evidence_ids=attempt.evidence_ids)
    reg=VerifierRegistry();reg.register(RenamedVerifier())
    with pytest.raises(ValueError,match='identity/version'):
        VerificationService(reg).verify(ob,r)


def test_forged_attempt_contents_rejected():
    _,r,_=_data();o=r.observations[0];ob=_obligation(r,o.observation_id,o.evidence_ids)
    class AlteredAttempt(ObservationContractVerifier):
        def verify(self,obligation,context):
            return replace(super().verify(obligation,context),details={'changed': True})
    reg=VerifierRegistry();reg.register(AlteredAttempt())
    with pytest.raises(ValueError,match='attempt identity'):
        VerificationService(reg).verify(ob,r)


def test_mutated_receipt_identity_rejected_by_rule():
    _,r,s=_data();o=r.observations[0];ob=_obligation(r,o.observation_id,o.evidence_ids)
    receipt=s.verify(ob,r)
    forged=replace(receipt,graph_fingerprint='other')
    rule=SemanticAuditRule(rule_id='r',version='1',obligation_type='observation_contract',title='r',finding_message='r')
    with pytest.raises(ValueError,match='receipt identity'):
        RuleEvaluator().evaluate(rule,ob,forged)


def test_protected_finding_rejects_forged_trigger():
    graph,r,s=_data();o=r.observations[0];ob=_obligation(r,o.observation_id,o.evidence_ids)
    receipt=s.verify(ob,r,semantic_graph=graph)
    rule=SemanticAuditRule(rule_id='r',version='1',obligation_type='observation_contract',title='r',finding_message='r',
        trigger_decision=VerificationDecision.REFUTED)
    fake=RuleEvaluationResult('r','1',receipt.receipt_id,ob.obligation_id,RuleDisposition.TRIGGERED,'fake')
    with pytest.raises(ValueError,match='independently replayed'):
        FindingFactory.create_verified(rule,fake,receipt,ob,r,semantic_graph=graph)


def test_protected_finding_positive_and_unrelated_evidence_blocked():
    graph,r,s=_data()
    o=next(o for o in r.observations if o.subject_id=='a')
    ob=_obligation(r,o.observation_id,o.evidence_ids)
    receipt=s.verify(ob,r,semantic_graph=graph)
    rule=SemanticAuditRule(rule_id='r',version='1',obligation_type='observation_contract',title='r',finding_message='r')
    evaluation=RuleEvaluator().evaluate(rule,ob,receipt)
    finding=FindingFactory.create_verified(rule,evaluation,receipt,ob,r,semantic_graph=graph)
    assert finding.receipt_id==receipt.receipt_id
    # Equivalent-looking receipt is not a different policy authority.
    evil=replace(receipt,evidence_ids=('other',))
    with pytest.raises(ValueError):
        FindingFactory.create_verified(rule,evaluation,evil,ob,r,semantic_graph=graph)


def _domain_data():
    graph=SemanticGraph()
    graph.add_node(SemanticNode('prod','Module',{'lifecycle':'production'}))
    graph.add_node(SemanticNode('exp','Module',{'lifecycle':'experimental'}))
    graph.add_edge(SemanticEdge('prod','exp','DEPENDS_ON',metadata={'source_id':'code:1'}))
    result=SemanticGraphAnalysisService(graph).analyze(GraphQuery('domain',QueryType.DEPENDENCY,['prod'],{'max_depth':1}))
    from audit_engine.semantic_audit.verification import GraphAttributeConstraintVerifier
    registry=VerifierRegistry();registry.register(GraphAttributeConstraintVerifier())
    return result,graph,VerificationService(registry)


def test_domain_entrypoint_rejects_direct_graph_list_corruption():
    dependency_result,domain_graph,verification_service=_domain_data()
    domain_graph.nodes.append(SemanticNode('prod','Module'))
    rule=DomainRuleLoader.from_yaml('specs/rules/architecture/no_production_to_experimental_dependency.yaml')
    with pytest.raises(ValueError,match='duplicate'):
        DomainRuleExecutor(verification_service).execute(rule,dependency_result,domain_graph)


def test_domain_entrypoint_preserves_unmatched_rule_status():
    dependency_result,domain_graph,verification_service=_domain_data()
    rule=DomainRuleLoader.from_mapping({'rule_id':'new.nomatch','version':'1',
        'domain':'architecture','obligation_type':'graph_attribute_constraint',
        'verifier_id':'graph-attribute-constraint','title':'no match','finding_message':'no match',
        'selector':{'scope':'observation','predicates':['INVALID']}})
    outcome=DomainRuleExecutor(verification_service).execute(rule,dependency_result,domain_graph)
    assert outcome.reason=='no_matching_targets' and outcome.obligations==() and outcome.findings==()
