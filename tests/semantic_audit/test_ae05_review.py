"""AE-05 independent acceptance fixtures: real sealed AE-01 and AE-04, no graph mocks."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
import pytest

from audit_engine.semantic_audit.ae01 import audit_repository
from audit_engine.semantic_audit.ae01.publication import canonical, sha
from audit_engine.semantic_audit.ae04 import build_campaign, publish_campaign
from audit_engine.semantic_audit.ae05 import (start_review, append_event, verify_review,
                                               initialize_review, append_review, verify_review_publication)

POLICY=Path(__file__).resolve().parents[2]/'specs/rules/architecture/no_production_to_experimental_dependency.yaml'


def fixture(tmp_path, kind='clean'):
    root=tmp_path/'src';root.mkdir()
    (root/'prod.py').write_text('import stable\n',encoding='utf8')
    (root/'stable.py').write_text('answer = 42\n',encoding='utf8')
    (root/'exp.py').write_text('',encoding='utf8')
    lifecycle={'prod':'production','stable':'stable','exp':'experimental'}
    before=tmp_path/'before';after=tmp_path/'after';campaign=tmp_path/'campaign'
    audit_repository(root,before,policy_file=POLICY,lifecycle=lifecycle)
    if kind=='changed': (root/'stable.py').write_text('answer = 43\n',encoding='utf8')
    if kind=='violation': (root/'prod.py').write_text('import exp\n',encoding='utf8')
    if kind=='incomplete': lifecycle={'prod':'production'}
    audit_repository(root,after,policy_file=POLICY,lifecycle=lifecycle)
    record=build_campaign(before,after)
    publish_campaign(record,campaign,before_output=before,after_output=after)
    return before,after,campaign,record


def _first(record,kind='source_task'):
    return next(o for o in record['packet']['obligations'] if o['kind']==kind)


def _verify(record,ctx):
    a,b,c,_=ctx
    return verify_review(record,c,a,b)


def test_clean_requires_explicit_human_review_without_certifying_global_correctness(tmp_path):
    ctx=fixture(tmp_path)
    journal=start_review(ctx[2],ctx[0],ctx[1])
    assert journal['state']['status']=='pending_human_review'
    assert len(journal['packet']['obligations'])==1
    guard=_first(journal,'campaign_gate')
    complete=append_event(journal,guard['id'],'acknowledge','reviewer-a','Checked bounded declared architecture evidence')
    assert complete['state']['bounded_review_recorded']
    assert not complete['state']['general_correctness_certified']
    assert len(complete['g3_memory']['records'])==1
    assert _verify(complete,ctx)['status']=='verified'


def test_changed_source_requires_review_and_preserves_campaign_nonpassing_status(tmp_path):
    ctx=fixture(tmp_path,'changed')
    assert ctx[3]['decision']['status']=='change_review_required'
    journal=start_review(ctx[2],ctx[0],ctx[1])
    assert any(row['kind']=='source_task' for row in journal['packet']['obligations'])
    for obligation in journal['packet']['obligations']:
        action='requires_action' if obligation['required_action']=='requires_action' else 'acknowledge'
        journal=append_event(journal,obligation['id'],action,'human','Reviewed exact changed source witnesses')
    assert not journal['state']['bounded_review_recorded']
    assert journal['state']['status'] in ('review_recorded_not_a_policy_pass','review_recorded_with_open_actions')
    assert _verify(journal,ctx)['status']=='verified'


def test_verified_defect_cannot_be_waived_by_human_acknowledgment(tmp_path):
    ctx=fixture(tmp_path,'violation')
    journal=start_review(ctx[2],ctx[0],ctx[1])
    p0=next(o for o in journal['packet']['obligations'] if o['priority']=='P0')
    with pytest.raises(ValueError,match='cannot be acknowledged'):
        append_event(journal,p0['id'],'acknowledge','reviewer','False clean claim')
    journal=append_event(journal,p0['id'],'requires_action','reviewer','Remediation and new source audit required')
    assert journal['state']['open_action_obligations']==[p0['id']]
    assert not journal['state']['bounded_review_recorded']
    assert _verify(journal,ctx)['status']=='verified'


def test_incomplete_classification_is_not_acknowledgable_as_clean(tmp_path):
    ctx=fixture(tmp_path,'incomplete')
    journal=start_review(ctx[2],ctx[0],ctx[1])
    guard=_first(journal,'campaign_gate')
    assert guard['required_action']=='requires_action'
    with pytest.raises(ValueError):append_event(journal,guard['id'],'acknowledge','r','All fine')
    assert not journal['packet']['architecture_clean_claim_within_scope']


def test_source_evidence_hash_and_campaign_bound_in_every_event(tmp_path):
    ctx=fixture(tmp_path,'violation')
    journal=start_review(ctx[2],ctx[0],ctx[1]); obligation=_first(journal)
    done=append_event(journal,obligation['id'],'dispute','researcher','Independent source inspection requested')
    event=done['events'][0]
    assert event['campaign_sha256']==ctx[3]['campaign_sha256']
    assert event['event_sha256']==sha(canonical({k:v for k,v in event.items() if k!='event_sha256'}))
    assert any(x in obligation['evidence_refs'] for x in event['evidence_refs'])
    assert _verify(done,ctx)['status']=='verified'


@pytest.mark.parametrize('field,value',[
    ('action','approved'),('actor',' '),('note',''),('obligation_id','invented')])
def test_invalid_reviews_rejected(tmp_path,field,value):
    ctx=fixture(tmp_path)
    journal=start_review(ctx[2],ctx[0],ctx[1]);ob=_first(journal,'campaign_gate')
    options={'obligation_id':ob['id'],'action':'acknowledge','actor':'human','note':'Scoped review performed'}
    options[field]=value
    with pytest.raises(ValueError): append_event(journal,**options)


def test_review_forged_evidence_reference_rejected(tmp_path):
    ctx=fixture(tmp_path)
    journal=start_review(ctx[2],ctx[0],ctx[1]);ob=_first(journal,'campaign_gate')
    with pytest.raises(ValueError,match='references'):
        append_event(journal,ob['id'],'acknowledge','r','Reviewed',evidence_refs=['arbitrary'])


def test_hash_chain_detects_reordering_and_deletion_even_with_resealed_top_level(tmp_path):
    ctx=fixture(tmp_path,'changed')
    start=start_review(ctx[2],ctx[0],ctx[1]);guard=_first(start,'campaign_gate');task=_first(start,'source_task')
    j=append_event(start,guard['id'],'requires_action','r','Policy review outstanding')
    j=append_event(j,task['id'],'acknowledge','r','Inspected change')
    for bad in (list(reversed(j['events'])),j['events'][1:]):
        altered=copy.deepcopy(j);altered['events']=bad
        altered['review_sha256']=sha(canonical({k:v for k,v in altered.items() if k!='review_sha256'}))
        with pytest.raises(ValueError): _verify(altered,ctx)


def test_canonical_payload_tamper_even_if_top_hash_resealed(tmp_path):
    ctx=fixture(tmp_path)
    j=start_review(ctx[2],ctx[0],ctx[1]);ob=_first(j,'campaign_gate')
    j=append_event(j,ob['id'],'acknowledge','r','Scoped evidence')
    for change in ('packet','memory','state'):
        bad=copy.deepcopy(j)
        if change=='packet': bad['packet']['obligations'][0]['priority']='P0'
        elif change=='memory': bad['g3_memory']['records']=[]
        else:bad['state']['bounded_review_recorded']=False
        bad['review_sha256']=sha(canonical({k:v for k,v in bad.items() if k!='review_sha256'}))
        with pytest.raises(ValueError): _verify(bad,ctx)


def test_publication_roundtrip_and_immutable_snapshots(tmp_path):
    before,after,campaign,_=fixture(tmp_path)
    out=tmp_path/'reviews'
    init=initialize_review(out,campaign_output=campaign,before_output=before,after_output=after)
    assert verify_review_publication(out,campaign_output=campaign,before_output=before,after_output=after)['journal_events']==0
    old=(out/'generations'/init['generation']/'review.json').read_bytes()
    ob=_first(start_review(campaign,before,after),'campaign_gate')
    next_=append_review(out,campaign_output=campaign,before_output=before,after_output=after,
                        obligation_id=ob['id'],action='acknowledge',actor='reviewer',note='Verified scope only')
    assert next_['generation']!=init['generation']
    assert (out/'generations'/init['generation']/'review.json').read_bytes()==old
    got=verify_review_publication(out,campaign_output=campaign,before_output=before,after_output=after)
    assert got['journal_events']==1 and got['review_state']['bounded_review_recorded']


def test_append_is_serialized_no_lost_review_events(tmp_path):
    before,after,campaign,_=fixture(tmp_path)
    out=tmp_path/'review'; initialize_review(out,campaign_output=campaign,before_output=before,after_output=after)
    ob=_first(start_review(campaign,before,after),'campaign_gate')
    def act(i):
        return append_review(out,campaign_output=campaign,before_output=before,after_output=after,
                   obligation_id=ob['id'],action='acknowledge',actor=f'reviewer-{i}',note=f'Independent review {i}')
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(act,range(2)))
    assert len({r['generation'] for r in results})==2
    assert verify_review_publication(out,campaign_output=campaign,before_output=before,after_output=after)['journal_events']==2


def test_failure_during_pointer_promotion_is_fail_closed(tmp_path,monkeypatch):
    before,after,campaign,_=fixture(tmp_path)
    out=tmp_path/'review';initialize_review(out,campaign_output=campaign,before_output=before,after_output=after)
    ob=_first(start_review(campaign,before,after),'campaign_gate')
    import audit_engine.semantic_audit.ae05.publication as pub
    original=pub._atomic_bytes
    def injected(path,data):
        if path.name=='LATEST.json' and b'"completed"' in data:
            raise OSError('injected interruption')
        return original(path,data)
    monkeypatch.setattr(pub,'_atomic_bytes',injected)
    with pytest.raises(OSError,match='interruption'):
        append_review(out,campaign_output=campaign,before_output=before,after_output=after,
                      obligation_id=ob['id'],action='acknowledge',actor='r',note='Review')
    with pytest.raises(ValueError,match='incomplete'):
        verify_review_publication(out,campaign_output=campaign,before_output=before,after_output=after)
    assert json.loads((out/'LATEST.json').read_bytes())['status']=='failed'


def test_published_report_and_seal_tampering_rejected(tmp_path):
    before,after,campaign,_=fixture(tmp_path)
    out=tmp_path/'review'
    init=initialize_review(out,campaign_output=campaign,before_output=before,after_output=after)
    p=out/'generations'/init['generation']/'review.json'
    p.write_bytes(p.read_bytes()+b' ')
    with pytest.raises(ValueError,match='sealed'):
        verify_review_publication(out,campaign_output=campaign,before_output=before,after_output=after)


def test_symlink_report_or_output_rejected(tmp_path):
    before,after,campaign,_=fixture(tmp_path)
    out=tmp_path/'review'
    result=initialize_review(out,campaign_output=campaign,before_output=before,after_output=after)
    report=out/'generations'/result['generation']/'review.json'
    backup=tmp_path/'report'; backup.write_bytes(report.read_bytes());report.unlink();report.symlink_to(backup)
    with pytest.raises(ValueError,match='Symlink'):
        verify_review_publication(out,campaign_output=campaign,before_output=before,after_output=after)
    link=tmp_path/'link';link.symlink_to(out,target_is_directory=True)
    with pytest.raises(ValueError,match='Symlink'):
        initialize_review(link,campaign_output=campaign,before_output=before,after_output=after)


def test_evidence_root_overlap_rejected(tmp_path):
    before,after,campaign,_=fixture(tmp_path)
    with pytest.raises(ValueError,match='overlaps'):
        initialize_review(campaign/'reviews',campaign_output=campaign,before_output=before,after_output=after)


def test_stale_campaign_replacement_invalidates_existing_review(tmp_path):
    before,after,campaign,_=fixture(tmp_path)
    out=tmp_path/'review';initialize_review(out,campaign_output=campaign,before_output=before,after_output=after)
    # AE-04 prior campaign remains sealed, but latest pointer deliberately fails.
    (campaign/'LATEST.json').write_bytes(canonical({'status':'failed','generation':None}))
    with pytest.raises(ValueError):
        verify_review_publication(out,campaign_output=campaign,before_output=before,after_output=after)


def test_cli_complete_review_and_bad_action_exit_codes(tmp_path):
    before,after,campaign,_=fixture(tmp_path)
    out=tmp_path/'review'
    args=['--output',str(out),'--campaign-output',str(campaign),
          '--before-output',str(before),'--after-output',str(after)]
    def run(command,*extra):
        return subprocess.run([sys.executable,'-m','audit_engine.semantic_audit.ae05',command,*args,*extra],
                              capture_output=True,text=True,timeout=30)
    init=run('init');assert init.returncode==3,init.stderr
    guard=_first(start_review(campaign,before,after),'campaign_gate')
    bad=run('record','--obligation-id','unknown','--action','acknowledge','--actor','r','--note','bad')
    assert bad.returncode==4
    good=run('record','--obligation-id',guard['id'],'--action','acknowledge',
             '--actor','reviewer','--note','Scoped review')
    assert good.returncode==0,good.stderr
    receipt=run('verify');assert receipt.returncode==0,receipt.stderr
    assert json.loads(receipt.stdout)['review_state']['bounded_review_recorded']


def test_existing_memory_record_payloads_are_immutable_snapshots(tmp_path):
    ctx=fixture(tmp_path)
    packet=start_review(ctx[2],ctx[0],ctx[1]);ob=_first(packet,'campaign_gate')
    done=append_event(packet,ob['id'],'acknowledge','r','Review')
    saved=copy.deepcopy(done)
    packet['packet']['obligations'][0]['priority']='P0'
    assert saved==done
    assert _verify(saved,ctx)['status']=='verified'


def test_mutation_evidence_is_replayed_before_human_review_is_trusted(tmp_path):
    from audit_engine.semantic_audit.ae03 import run_experiment
    src=tmp_path/'src';src.mkdir();(src/'tests').mkdir()
    (src/'prod.py').write_text('import stable\ndef predicate(v):\n    return v == 7\n')
    (src/'stable.py').write_text('')
    (src/'tests'/'test_prod.py').write_text(
        'from prod import predicate\ndef test_value():\n    assert predicate(7)\n    assert not predicate(4)\n')
    before,after=tmp_path/'before',tmp_path/'after'
    labels={'prod':'production','stable':'stable','tests.test_prod':'stable'}
    audit_repository(src,before,lifecycle=labels,policy_file=POLICY)
    audit_repository(src,after,lifecycle=labels,policy_file=POLICY)
    mutation=run_experiment(src,['prod.py'],['tests/test_prod.py'],max_mutants=1,timeout=15)
    assert mutation['counts']['killed']==1
    c=build_campaign(before,after,mutation_record=mutation,mutation_root=src,
                     replay_mutation=True,require_mutation=True)
    camp=tmp_path/'campaign'
    publish_campaign(c,camp,before_output=before,after_output=after,
                     mutation_root=src,replay_mutation=True)
    with pytest.raises(ValueError):start_review(camp,before,after)
    journal=start_review(camp,before,after,mutation_root=src,replay_mutation=True)
    assert journal['packet']['decision_status']=='bounded_architecture_policy_pass'
    assert verify_review(journal,camp,before,after,mutation_root=src,replay_mutation=True)['status']=='verified'
    (src/'prod.py').write_text('import stable\ndef predicate(v):\n    return v != 7\n')
    with pytest.raises(ValueError):
        verify_review(journal,camp,before,after,mutation_root=src,replay_mutation=True)


def test_old_ledger_cannot_be_rebound_to_new_campaign(tmp_path):
    before,after,campaign,_=fixture(tmp_path,'clean')
    prior=start_review(campaign,before,after)
    # A second genuinely distinct source generation, then published AE-04 campaign.
    source=tmp_path/'other_source';source.mkdir()
    (source/'prod.py').write_text('import stable\n')
    (source/'stable.py').write_text('value=5\n')
    audit_repository(source,tmp_path/'new_after',policy_file=POLICY,
                     lifecycle={'prod':'production','stable':'stable'})
    r=build_campaign(before,tmp_path/'new_after')
    other=tmp_path/'other_campaign'
    publish_campaign(r,other,before_output=before,after_output=tmp_path/'new_after')
    with pytest.raises(ValueError,match='campaign changed|obligation evidence'):
        verify_review(prior,other,before,tmp_path/'new_after')
