"""AE-17: independent source-replay, uncertainty, retrieval, tamper and memory controls."""
import copy
import json

import pytest

from audit_engine.semantic_audit.ae01.publication import canonical
from audit_engine.semantic_audit.ae16.publication import publish_observation
from audit_engine.semantic_audit.ae17 import (
    build_investigation, publish_investigation, verify_investigation,
    record_investigation, retrieve_snapshot_history, plan_registered_verification,
)
from audit_engine.semantic_audit.evolution.memory import AuditLongTermMemory


def basic_decl():
    return {'schema':'ae16/declared_execution/v1','run_id':'investigation-case',
            'reported_status':'success',
            'jobs':[{'id':'build','status':'success','needs':[],
                     'steps':[{'id':'tests','status':'success','exit_code':0,
                               'log':'step.log',
                               'checks':[{'id':'mandatory','status':'skipped','tests':[]}],
                               'produces':[{'id':'package','path':'producer.dat'}],
                               'consumes':[]}]},
                    {'id':'consume','status':'success','needs':['build'],
                     'steps':[{'id':'read','status':'success','exit_code':0,
                               'log':'consume.log',
                               'checks':[{'id':'read_check','status':'passed','tests':[
                                   {'id':'unit','expected':'passed','observed':'passed'}]}],
                               'produces':[],
                               'consumes':[{'id':'package','path':'consumer.dat'}]}]}],
            'requirements':[{'id':'req1','job':'build','step':'tests','check':'mandatory'}]}


@pytest.fixture
def lab(tmp_path):
    evidence=tmp_path/'evidence';evidence.mkdir()
    (evidence/'step.log').write_text('test skipped',encoding='utf-8')
    (evidence/'consume.log').write_text('step succeeded',encoding='utf-8')
    (evidence/'producer.dat').write_bytes(b'producer version')
    (evidence/'consumer.dat').write_bytes(b'unexpected consumer version')
    declaration=tmp_path/'run.json';declaration.write_bytes(canonical(basic_decl()))
    ae16=tmp_path/'ae16';publish_observation(declaration,evidence,ae16)
    return declaration,evidence,ae16,tmp_path/'ae17'


def test_verified_upstream_generates_alternatives_not_findings(lab):
    decl,evidence,upstream,_=lab
    result=build_investigation(decl,evidence,upstream)
    assert result['schema']=='ae17/bounded_investigation/v1'
    assert result['verified_findings']==[] and result['verified_root_causes']==[]
    assert result['verification_execution']=='not_performed'
    assert result['epistemic_status']=='investigation_hypotheses_only'
    assert result['observed_issues']>=2
    issues={c['issue']['kind'] for c in result['cases']}
    assert 'producer_consumer_content_mismatch' in issues
    assert 'required_check_not_satisfied' in issues
    for case in result['cases']:
        assert len(case['alternatives'])>=2
        assert all(h['epistemic_status']=='unverified_possible_explanation' for h in case['alternatives'])


def test_source_retrieval_uses_existing_graph_and_digests(lab):
    decl,evidence,upstream,_=lab
    result=build_investigation(decl,evidence,upstream)
    case=next(c for c in result['cases'] if c['issue']['kind']=='required_check_not_satisfied')
    assert case['context']['subject_found_in_graph']
    assert case['context']['relationships']
    assert case['retrieval_scope']=='bounded_one_hop_source_graph'


def test_replayable_publication_idempotent(lab):
    decl,evidence,upstream,out=lab
    one=publish_investigation(decl,evidence,upstream,out)
    assert one['assurance']=='unverified_hypothesis_plan_only'
    assert verify_investigation(decl,evidence,upstream,out)==one
    assert publish_investigation(decl,evidence,upstream,out)==one
    assert len(list((out/'generations').iterdir()))==1


def test_source_change_invalidates_ae16_and_investigation(lab):
    decl,evidence,upstream,out=lab
    publish_investigation(decl,evidence,upstream,out)
    (evidence/'producer.dat').write_bytes(b'changed source')
    with pytest.raises(ValueError):verify_investigation(decl,evidence,upstream,out)
    with pytest.raises(ValueError):build_investigation(decl,evidence,upstream)


def test_declaration_change_invalidates(lab):
    decl,evidence,upstream,out=lab
    publish_investigation(decl,evidence,upstream,out)
    doc=basic_decl();doc['run_id']='different';decl.write_bytes(canonical(doc))
    with pytest.raises(ValueError):verify_investigation(decl,evidence,upstream,out)


def test_seal_and_report_tamper_refused(lab):
    decl,evidence,upstream,out=lab
    first=publish_investigation(decl,evidence,upstream,out)
    folder=out/'generations'/first['generation']
    report=folder/'investigation.json'
    doc=json.loads(report.read_bytes());doc['verified_findings']=[{'false':'claim'}]
    report.write_bytes(canonical(doc))
    with pytest.raises(ValueError):verify_investigation(decl,evidence,upstream,out)


def test_rehashed_revised_report_cannot_forge_source(lab):
    from audit_engine.semantic_audit.ae01.publication import sha
    decl,evidence,upstream,out=lab
    first=publish_investigation(decl,evidence,upstream,out)
    folder=out/'generations'/first['generation']
    report=json.loads((folder/'investigation.json').read_bytes())
    report['cases'][0]['alternatives'][0]['statement']='forged cause'
    blob=canonical(report)
    (folder/'investigation.json').write_bytes(blob)
    (folder/'SEAL.json').write_bytes(canonical({'schema':'ae17/investigation_seal/v1',
        'artifacts':{'investigation.json':sha(blob)}}))
    (out/'LATEST.json').write_bytes(canonical({'status':'completed','generation':first['generation'],
        'seal_sha256':sha((folder/'SEAL.json').read_bytes())}))
    with pytest.raises(ValueError):verify_investigation(decl,evidence,upstream,out)


def test_context_budget_and_case_budget(lab):
    decl,evidence,upstream,_=lab
    plan=build_investigation(decl,evidence,upstream,max_cases=1,max_context=1)
    assert plan['selected_issues']==1
    assert plan['truncated']
    assert all(len(c['context']['relationships'])<=1 for c in plan['cases'])
    assert all(isinstance(c['context']['truncated'],bool) for c in plan['cases'])


@pytest.mark.parametrize('field,value', [('max_cases',0),('max_context',0),('max_cases',81),('max_context',65),('max_cases',True)])
def test_invalid_budgets(lab,field,value):
    decl,evidence,upstream,_=lab
    with pytest.raises(ValueError):build_investigation(decl,evidence,upstream,**{field:value})


def test_unknown_issue_keeps_unverified_fallback(monkeypatch,lab):
    from audit_engine.semantic_audit.ae17 import investigate as mod
    assert mod.HYPOTHESES.get('hypothetical_new_issue') is None
    assert len(mod.FALLBACK)>=2
    assert all('may' in item[1].lower() or 'unresolved' in item[1].lower() for item in mod.FALLBACK)


def test_memory_snapshot_scoped_not_current_evidence(lab):
    decl,evidence,upstream,_=lab
    report=build_investigation(decl,evidence,upstream)
    memory=AuditLongTermMemory();a=record_investigation(memory,report)
    assert a.snapshot_id==report['snapshot_id']
    result=retrieve_snapshot_history(memory,report['snapshot_id'])
    assert result['historical_not_current_evidence']
    assert len(result['records'])==1
    assert not retrieve_snapshot_history(memory,'different')['records']
    assert len(memory)==1


def test_memory_cannot_store_claimed_finding(lab):
    decl,evidence,upstream,_=lab
    report=build_investigation(decl,evidence,upstream)
    modified=copy.deepcopy(report);modified['verified_findings']=[{'made_up':True}]
    with pytest.raises(ValueError):record_investigation(AuditLongTermMemory(),modified)


def test_planner_requires_real_registered_obligations():
    with pytest.raises(ValueError):plan_registered_verification(obligations=[],objectives=[],
                registry=None,profiles=None,budget=None)


def test_reject_output_overlapping_source(lab):
    decl,evidence,upstream,_=lab
    with pytest.raises(ValueError):publish_investigation(decl,evidence,upstream,evidence/'out')


def test_no_execution_and_no_authority_implicit(lab):
    decl,evidence,upstream,_=lab
    report=build_investigation(decl,evidence,upstream)
    assert 'authenticated' not in report['evidence_authority'] or 'not_authenticated' in report['evidence_authority']
    assert report['source_authority']=='untrusted_execution_declaration_not_github_authenticated'
    assert report['next_step']=='supply_independent_evidence_and_registered_verification_obligations'
