"""D2: explicit observation↔evidence relationships and bounded G3 verification.

The existing G3 source analysis remains authoritative for the observation's
*declared* evidence IDs; this bridge refuses arbitrary Cartesian products.
Verification proves only stated graph-observation contracts, not Python truth.
"""
from __future__ import annotations
from collections import defaultdict
from typing import Any

from audit_engine.semantic_audit.graph.analysis import AnalysisStatus, VerificationStatus
from audit_engine.semantic_audit.verification import (VerificationDecision,
    VerificationService, VerificationObligation, VerifierRegistry,
    ObservationContractVerifier)
from audit_engine.semantic_audit.graph.analysis.identity import deterministic_id, edge_fingerprint
from .admission import validate_graph
from audit_engine.semantic_audit.core.semantic_graph import SemanticEdge
from .identity import content_id, digest

SCHEMA = 'ae13/association_registry/v1'
PLAN_SCHEMA = 'ae13/verification_plan/v1'


def admit_analysis(result, *, graph=None) -> dict[str, Any]:
    """Validate complete G3 evidence membership, not just existence in one result.

    Each relationship ID is stable in the source analysis and retains a unique
    `(observation,evidence)` pair. One-to-many/many-to-one are both legal.
    """
    graph_admission=None
    if graph is not None:
        graph_admission=validate_graph(graph)
        if graph_admission['graph_fingerprint']!=result.graph_fingerprint:
            raise ValueError('Source graph does not match source analysis fingerprint')
        allowed_edges={edge_fingerprint(edge) for edge in graph.edges}
        for witness in result.evidence:
            if witness.source_kind=='semantic_edge' and witness.evidence_id not in allowed_edges:
                raise ValueError('Witness is not present in admitted source graph')
    observations={}; evidence={}
    for e in result.evidence:
        if not isinstance(e.evidence_id,str) or not e.evidence_id or e.evidence_id in evidence:
            raise ValueError('Duplicate or empty evidence identity')
        if e.source_kind == 'semantic_edge':
            source=e.provenance if isinstance(e.provenance,dict) else {}
            if not isinstance(source.get('edge_attributes'),dict) or not isinstance(source.get('edge_metadata'),dict):
                raise ValueError('Missing direct edge provenance')
            reconstructed=SemanticEdge(e.subject_id,e.object_id,e.predicate,
                                      attributes=source['edge_attributes'],metadata=source['edge_metadata'])
            if edge_fingerprint(reconstructed)!=e.evidence_id:
                raise ValueError('Forged direct edge witness identity')
        evidence[e.evidence_id]=e
    for o in result.observations:
        if not isinstance(o.observation_id,str) or not o.observation_id or o.observation_id in observations:
            raise ValueError('Duplicate or empty observation identity')
        observations[o.observation_id]=o
    links=[]
    for obs in result.observations:
        if len(obs.evidence_ids)!=len(set(obs.evidence_ids)):
            raise ValueError('Duplicate evidence associations inside observation')
        if not obs.evidence_ids:
            # Unsupported source facts may exist, but they are not admitted as
            # verifiable source-backed observations by this bridge.
            continue
        for evid in obs.evidence_ids:
            if evid not in evidence:
                raise ValueError('Observation references foreign evidence')
            witness=evidence[evid]
            if witness.source_kind == 'semantic_edge' and (witness.subject_id,witness.predicate,witness.object_id)!=(obs.subject_id,obs.predicate,obs.object_id):
                raise ValueError('Direct edge witness does not match source observation')
            links.append({'observation_id':obs.observation_id,'evidence_id':evid,
                          'link_id':content_id('association',[result.analysis_id,obs.observation_id,evid])})
    links.sort(key=lambda x:(x['observation_id'],x['evidence_id']))
    # Bind exact bytes of the declared analysis; no claim that its model is sound.
    result_bytes=result.to_dict()
    registry={'schema':SCHEMA,'source_analysis_id':result.analysis_id,
              'analysis_sha256':digest(result_bytes), 'graph_fingerprint':result.graph_fingerprint,
              'semantic_context_fingerprint':result.semantic_context.fingerprint,
              'graph_admission':graph_admission,
              'links':links,'unlinked_observation_ids':sorted(o.observation_id for o in result.observations if not o.evidence_ids),
              'orphan_evidence_ids':sorted(set(evidence)-{l['evidence_id'] for l in links})}
    registry['registry_id']=content_id('association-registry',registry)
    return registry


def verify_registry(registry, result, *, graph=None):
    if registry != admit_analysis(result,graph=graph):
        raise ValueError('Evidence association registry stale or rehashed incorrectly')
    return True


def create_obligation(result, registry:dict, *, selected_observations:tuple[str,...],
                      quantifier:str='all', property_name:str='observed_graph_triple',
                      verifier_id:str='observation-contract') -> dict:
    """One plan may join many source observations; one observation may join many plans.

    A plan records *all* witnesses for each selected observation, not an
    arbitrary unattached evidence list. 'all' and 'any' have different semantics.
    """
    if registry.get('graph_admission') is None:
        verify_registry(registry,result)
    else:
        # Enrollment is verified at run_bound_verification with actual graph.
        if (registry.get('source_analysis_id')!=result.analysis_id or
            registry.get('analysis_sha256')!=digest(result.to_dict())):
            raise ValueError('Attested registry is stale')
    if quantifier not in ('all','any'):
        raise ValueError('Unknown quantifier')
    if property_name!='observed_graph_triple' or verifier_id!='observation-contract':
        raise ValueError('Unsupported property/verifier combination')
    if not selected_observations or len(set(selected_observations))!=len(selected_observations):
        raise ValueError('Empty or repeated observation selection')
    obs={o.observation_id:o for o in result.observations}
    links_by_obs=defaultdict(list)
    for link in registry['links']:
        links_by_obs[link['observation_id']].append(link)
    entries=[]
    for oid in sorted(selected_observations):
        if oid not in obs or not links_by_obs[oid]:
            raise ValueError('Missing observation or its evidence associations')
        o=obs[oid]
        entries.append({'observation_id':oid,'witness_links':links_by_obs[oid],
                        'expected':{'subject_id':o.subject_id,'predicate':o.predicate,'object_id':o.object_id}})
    payload={'schema':PLAN_SCHEMA,'registry_id':registry['registry_id'],
             'source_analysis_id':result.analysis_id,'graph_fingerprint':result.graph_fingerprint,
             'semantic_context_fingerprint':result.semantic_context.fingerprint,
             'quantifier':quantifier,'property_name':property_name,'verifier_id':verifier_id,
             'entries':entries}
    payload['plan_id']=content_id('association-plan',payload)
    return payload


def _verify_plan(plan,result,registry):
    if plan.get('plan_id')!=content_id('association-plan',{k:v for k,v in plan.items() if k!='plan_id'}):
        raise ValueError('Plan identity incorrect')
    replay=create_obligation(result,registry,selected_observations=tuple(e['observation_id'] for e in plan['entries']),
                             quantifier=plan['quantifier'],property_name=plan['property_name'],verifier_id=plan['verifier_id'])
    if replay!=plan:
        raise ValueError('Plan relationship or required witness altered')


def run_bound_verification(result, registry, plan, *, registry_of_verifiers=None, graph=None) -> dict:
    """Run one existing G3 verification per selected occurrence, then aggregate.

    No new verifier authority; explicit postconditions prevent a mismatched
    verifier descriptor/receipt or unrelated witness from passing the gate.
    """
    verify_registry(registry,result,graph=graph)
    _verify_plan(plan,result,registry)
    reg=registry_of_verifiers or VerifierRegistry()
    if registry_of_verifiers is None:
        reg.register(ObservationContractVerifier())
    service=VerificationService(reg)
    receipts=[]
    for ent in plan['entries']:
        ev_ids=tuple(sorted(l['evidence_id'] for l in ent['witness_links']))
        obligation=VerificationObligation.from_analysis_result(result,obligation_type='observation_contract',
            observation_ids=[ent['observation_id']],evidence_ids=ev_ids,
            requested_verifier_ids=[plan['verifier_id']],parameters=ent['expected'])
        verifier=reg.get(plan['verifier_id'])
        if verifier is None or type(verifier) is not ObservationContractVerifier:
            raise ValueError('Bound graph contract requires the pinned built-in verifier')
        receipt=service.verify(obligation,result,verifier_id=plan['verifier_id'],semantic_graph=graph)
        desc=verifier.descriptor
        if (receipt.verifier_id!=desc.verifier_id or receipt.verifier_version!=desc.version or
            receipt.obligation_id!=obligation.obligation_id or receipt.source_analysis_id!=result.analysis_id or
            receipt.graph_fingerprint!=result.graph_fingerprint or
            receipt.semantic_context_fingerprint!=result.semantic_context.fingerprint or
            tuple(sorted(receipt.evidence_ids))!=ev_ids):
            raise ValueError('Verifier returned misbound receipt')
        # Recompute receipt identity from immutable payload contract (G3.1).
        record=receipt.to_dict()
        signed={key:record[key] for key in ('attempt_id','obligation_id','source_analysis_id','verifier_id',
            'verifier_version','decision','evidence_state','evidence_ids','graph_fingerprint',
            'semantic_context_fingerprint','details','error')}
        if receipt.receipt_id!=deterministic_id('verification-receipt',signed,length=24):
            raise ValueError('Verification receipt identity mismatch')
        receipts.append({'observation_id':ent['observation_id'],'receipt_id':receipt.receipt_id,
                         'decision':receipt.decision.value,'evidence_state':receipt.evidence_state.value,
                         'evidence_ids':list(ev_ids)})
    if graph is not None and validate_graph(graph)['graph_fingerprint']!=result.graph_fingerprint:
        raise ValueError('Source graph changed during verification')
    confirmations=[r['decision']==VerificationDecision.CONFIRMED.value and r['evidence_state']==VerificationStatus.VALIDATED.value for r in receipts]
    if plan['quantifier']=='all':
        accepted=all(confirmations)
    else:
        accepted=any(confirmations)
    outcome={'schema':'ae13/bound_graph_contract_result/v1',
             'plan_id':plan['plan_id'],'registry_id':registry['registry_id'],
             'quantifier':plan['quantifier'],'receipts':receipts,
             'decision':(('confirmed_within_attested_graph_contract' if graph is not None else 'confirmed_within_declared_graph_contract') if accepted else 'not_confirmed'),
             'scope_warning':'G3 observation-contract verification is not proof of executable Python behavior'}
    outcome['result_id']=content_id('bound-verification',outcome)
    return outcome
