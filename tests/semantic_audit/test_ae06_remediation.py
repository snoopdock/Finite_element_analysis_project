"""AE-06 adversarial tests exercise real sealed G3/AE-01/04/05 services."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import subprocess
import sys
import pytest

from audit_engine.semantic_audit.ae01 import audit_repository
from audit_engine.semantic_audit.ae01.publication import canonical,sha
from audit_engine.semantic_audit.ae04 import build_campaign,publish_campaign
from audit_engine.semantic_audit.ae05 import initialize_review,append_review,verify_review_publication
from audit_engine.semantic_audit.ae06 import (build_assessment,verify_assessment,
                    publish_assessment,verify_assessment_publication)

POLICY=Path(__file__).resolve().parents[2]/'specs/rules/architecture/no_production_to_experimental_dependency.yaml'
LIFE={'prod':'production','stable':'stable','exp':'experimental','exp2':'experimental','secondary':'production'}


def make(tmp_path,mode='repaired',*,review='requires_action', current_life=None):
    src=tmp_path/'src';src.mkdir()
    (src/'prod.py').write_text('import stable\n',encoding='utf8')
    for name in ('stable','exp','exp2','secondary'):
        (src/f'{name}.py').write_text('meaning = 10\n',encoding='utf8')
    before, flagged, current = (tmp_path/n for n in ('before','flagged','current'))
    audit_repository(src,before,policy_file=POLICY,lifecycle=LIFE)
    (src/'prod.py').write_text('import exp\n',encoding='utf8')
    audit_repository(src,flagged,policy_file=POLICY,lifecycle=LIFE)
    original=tmp_path/'original_campaign'; journal=tmp_path/'review'
    a=build_campaign(before,flagged)
    publish_campaign(a,original,before_output=before,after_output=flagged)
    initialize_review(journal,campaign_output=original,before_output=before,after_output=flagged)
    if review != 'absent':
        receipt=verify_review_publication(journal,campaign_output=original,before_output=before,after_output=flagged)
        for ob in receipt['obligations']:
            action = review if ob['priority']=='P0' else 'requires_action'
            append_review(journal,campaign_output=original,before_output=before,after_output=flagged,
                          obligation_id=ob['id'],action=action,actor='unverified-label',
                          note='Investigate source evidence and seek separate reviewer authorization')
    if mode == 'repaired':code='import stable\n# remediation hypothesis\n'
    elif mode == 'persistent':code='import exp\n'
    elif mode == 'different':code='import exp2\n'
    elif mode == 'empty':code='value = 2\n'
    elif mode == 'missing':code=None
    elif mode == 'new_unrelated':code='import stable\n'
    elif mode == 'comment_only':code='import exp\n# comment does not fix violation\n'
    elif mode == 'unknown':code='import mystery_dynamic_target\n'
    else:raise ValueError(mode)
    if code is None:(src/'prod.py').unlink()
    else:(src/'prod.py').write_text(code,encoding='utf8')
    if mode == 'new_unrelated':(src/'secondary.py').write_text('import exp\n',encoding='utf8')
    audit_repository(src,current,policy_file=POLICY,lifecycle=current_life or LIFE)
    followup=tmp_path/'followup_campaign'
    f=build_campaign(flagged,current)
    publish_campaign(f,followup,before_output=flagged,after_output=current)
    return dict(origin_before=before,flagged_output=flagged,current_output=current,
                origin_campaign=original,origin_review=journal,followup_campaign=followup)


def assess(inputs):return build_assessment(**inputs)


def test_repaired_source_yields_only_bounded_absence_candidate(tmp_path):
    inputs=make(tmp_path)
    record=assess(inputs)
    assert record['assurance']['status']=='bounded_absence_candidates_require_human_closure'
    assert record['cases'][0]['status']=='bounded_absence_candidate'
    assert record['cases'][0]['old_source_sha256']!=record['cases'][0]['current_source_sha256']
    assert record['cases'][0]['current_source_rule_executed']
    assert all(record['assurance'][x] is False for x in ('reviewer_identity_authenticated','remediation_causality_proven','global_software_correctness_certified'))
    assert verify_assessment(record,**inputs)['verification']=='rederived_from_ae01_ae04_ae05'

@pytest.mark.parametrize('mode,status',[
    ('persistent','persistent_violation'),
    ('comment_only','persistent_violation'),
    ('different','changed_violation_open'),
    ('empty','not_assessable'),
    ('missing','not_assessable'),
    ('unknown','not_assessable'),
    ('new_unrelated','bounded_absence_candidate'),
])
def test_prohibition_status_remains_conservative(tmp_path,mode,status):
    inputs=make(tmp_path,mode)
    r=assess(inputs)
    assert r['cases'][0]['status']==status
    if mode=='new_unrelated':
        assert r['assurance']['open_finding_count']==1
        assert r['assurance']['status']=='verified_violation_requires_action'
        assert r['new_finding_ids']
        assert r['new_dependency_signatures'] == [{
            'rule_id':'architecture.no_production_to_experimental_dependency',
            'source_file':'secondary.py','target_module':'exp'}]
    else:
        assert r['assurance']['status']!='bounded_absence_candidates_require_human_closure'

@pytest.mark.parametrize('review', ['absent','dispute'])
def test_human_dispute_or_missing_review_never_authorizes_closure(tmp_path,review):
    inp=make(tmp_path,review=review)
    r=assess(inp)
    assert r['cases'][0]['status']=='review_required'
    assert 'remediation_review_not_recorded' in r['cases'][0]['reasons']


def test_lifecycle_change_invalidates_comparability(tmp_path):
    altered={**LIFE,'exp':'stable'}
    inp=make(tmp_path,current_life=altered)
    r=assess(inp)
    assert r['cases'][0]['status']=='not_assessable'
    assert 'policy_or_classification_changed' in r['cases'][0]['reasons']


def test_missing_classification_is_not_clean(tmp_path):
    inp=make(tmp_path,current_life={'prod':'production'})
    r=assess(inp)
    assert r['cases'][0]['status']=='not_assessable'
    assert not r['assurance']['global_software_correctness_certified']


def test_source_without_required_rule_cannot_be_declared_repaired(tmp_path):
    r=assess(make(tmp_path,'empty'))
    assert 'source_rule_not_executed_on_current_dependency' in r['cases'][0]['reasons']


def test_modified_in_memory_assessment_is_rejected(tmp_path):
    inp=make(tmp_path);r=assess(inp)
    r['assurance']['status']='bounded_clean_certified'
    with pytest.raises(ValueError,match='hash mismatch'):
        verify_assessment(r,**inp)


def test_rehashed_but_false_remediation_claim_is_rejected(tmp_path):
    inp=make(tmp_path,'persistent');r=assess(inp)
    r['cases'][0]['status']='bounded_absence_candidate'
    r['assurance']['status']='bounded_absence_candidates_require_human_closure'
    r['assessment_sha256']=sha(canonical({k:v for k,v in r.items() if k!='assessment_sha256'}))
    with pytest.raises(ValueError,match='disagrees'):
        verify_assessment(r,**inp)


def test_wrong_followup_campaign_endpoints_rejected(tmp_path):
    inp=make(tmp_path)
    inp['current_output']=inp['origin_before']
    with pytest.raises(ValueError):assess(inp)


def test_tampered_review_publication_rejected(tmp_path):
    inp=make(tmp_path)
    f=inp['origin_review']/'LATEST.json';f.write_text('{"status":"failed"}')
    with pytest.raises(ValueError):assess(inp)


def test_tampered_campaign_publication_rejected(tmp_path):
    inp=make(tmp_path)
    gen=json.loads((inp['followup_campaign']/'LATEST.json').read_text())['generation']
    f=inp['followup_campaign']/'generations'/gen/'campaign.json'
    f.write_text(f.read_text()+'\n')
    with pytest.raises(ValueError):assess(inp)


def test_tampered_source_manifest_rejected(tmp_path):
    inp=make(tmp_path)
    gen=json.loads((inp['current_output']/'LATEST.json').read_text())['generation']
    f=inp['current_output']/'generations'/gen/'manifest.json';f.write_text('{}')
    with pytest.raises(ValueError):assess(inp)


def test_publication_and_detached_rederivation(tmp_path):
    inp=make(tmp_path);r=assess(inp);out=tmp_path/'ae06_publication'
    receipt=publish_assessment(r,out,**inp)
    assert receipt['status']=='bounded_absence_candidates_require_human_closure'
    assert receipt['generation'].startswith('ae06-')
    assert verify_assessment_publication(out,**inp)['assessment_sha256']==r['assessment_sha256']
    assert publish_assessment(r,out,**inp)['generation']==receipt['generation']


def test_publication_failure_cannot_keep_previous_current_success(tmp_path):
    inp=make(tmp_path);r=assess(inp);out=tmp_path/'publish'
    publish_assessment(r,out,**inp)
    forged=copy.deepcopy(r);forged['assurance']['status']='forged'
    with pytest.raises(ValueError):publish_assessment(forged,out,**inp)
    assert json.loads((out/'LATEST.json').read_text())['status']=='failed'
    with pytest.raises(ValueError,match='LATEST'):
        verify_assessment_publication(out,**inp)


def test_publication_tamper_and_symlink_rejected(tmp_path):
    inp=make(tmp_path);r=assess(inp);out=tmp_path/'publish'
    receipt=publish_assessment(r,out,**inp)
    f=out/'generations'/receipt['generation']/'assessment.json'
    f.write_bytes(f.read_bytes()+b' ')
    with pytest.raises(ValueError):verify_assessment_publication(out,**inp)
    with pytest.raises(ValueError):publish_assessment(r,out,**inp)


def test_symlink_output_root_and_overlap_are_rejected(tmp_path):
    inp=make(tmp_path);r=assess(inp)
    (tmp_path/'alias').symlink_to(tmp_path/'actual',target_is_directory=True)
    with pytest.raises((ValueError,OSError)):
        publish_assessment(r,tmp_path/'alias',**inp)
    with pytest.raises(ValueError,match='overlap'):
        publish_assessment(r,inp['flagged_output']/'inside',**inp)


def test_history_without_proven_adjacent_campaigns_rejected(tmp_path):
    inp=make(tmp_path)
    with pytest.raises(ValueError,match='sealed campaign'):
        assess({**inp,'history_outputs':(inp['origin_before'],)})


def test_ordered_three_generation_regression_detection(tmp_path):
    inp=make(tmp_path,'persistent')
    root=tmp_path/'src';historical=tmp_path/'historical'
    (root/'prod.py').write_text('import stable\n# intermediate clean\n',encoding='utf8')
    audit_repository(root,historical,policy_file=POLICY,lifecycle=LIFE)
    ca=tmp_path/'history_a';cb=tmp_path/'history_b'
    a=build_campaign(inp['flagged_output'],historical)
    publish_campaign(a,ca,before_output=inp['flagged_output'],after_output=historical)
    b=build_campaign(historical,inp['current_output'])
    publish_campaign(b,cb,before_output=historical,after_output=inp['current_output'])
    options={**inp,'history_outputs':(historical,), 'history_campaigns':(ca,cb)}
    r=assess(options)
    assert r['cases'][0]['status']=='reintroduced_violation'
    assert len(r['inputs']['history_campaign_sha256'])==2
    assert verify_assessment(r,**options)['status']=='verified_violation_requires_action'


def test_broken_history_link_rejected(tmp_path):
    inp=make(tmp_path,'persistent')
    historical=tmp_path/'historical';root=tmp_path/'src'
    (root/'prod.py').write_text('import stable\n',encoding='utf8')
    audit_repository(root,historical,policy_file=POLICY,lifecycle=LIFE)
    bad_link=tmp_path/'bad_link'
    publish_campaign(build_campaign(inp['origin_before'],historical),bad_link,
                     before_output=inp['origin_before'],after_output=historical)
    with pytest.raises(ValueError):
        assess({**inp,'history_outputs':(historical,), 'history_campaigns':(bad_link,bad_link)})


def test_history_is_bounded(tmp_path):
    inp=make(tmp_path)
    with pytest.raises(ValueError,match='bounded'):
        assess({**inp,'history_outputs':tuple(inp['origin_before'] for _ in range(33))})


def test_cli_publish_and_verify_in_trusted_fixture(tmp_path):
    inp=make(tmp_path);out=tmp_path/'cli'
    flags=[]
    for name,value in inp.items():flags.extend(['--'+name.replace('_','-'),str(value)])
    first=subprocess.run([sys.executable,'-m','audit_engine.semantic_audit.ae06','publish',
                          '--output',str(out),*flags],capture_output=True,text=True,timeout=25)
    assert first.returncode==0,first.stderr
    result=json.loads(first.stdout)
    assert result['status']=='bounded_absence_candidates_require_human_closure'
    second=subprocess.run([sys.executable,'-m','audit_engine.semantic_audit.ae06','verify',
                          '--output',str(out),*flags],capture_output=True,text=True,timeout=25)
    assert second.returncode==0,second.stderr
    assert json.loads(second.stdout)['assessment_sha256']==result['assessment_sha256']


def test_previous_dependency_target_removed_from_scope_is_inconclusive(tmp_path):
    inp=make(tmp_path)
    # Construct a NEW independently sealed audit where exp.py is removed.
    # Do not mutate already sealed current evidence; generate a new follow-up.
    root=tmp_path/'src';(root/'exp.py').unlink()
    later=tmp_path/'no_exp';audit_repository(root,later,policy_file=POLICY,lifecycle=LIFE)
    campaign=tmp_path/'no_exp_campaign'
    publish_campaign(build_campaign(inp['flagged_output'],later),campaign,
                     before_output=inp['flagged_output'],after_output=later)
    r=assess({**inp,'current_output':later,'followup_campaign':campaign})
    assert r['cases'][0]['status']=='not_assessable'
    assert 'previous_target_module_left_audit_scope' in r['cases'][0]['reasons']


def test_changed_review_journal_invalidates_prior_closure_candidate(tmp_path):
    inp=make(tmp_path);old=assess(inp)
    state=verify_review_publication(inp['origin_review'],campaign_output=inp['origin_campaign'],
                                    before_output=inp['origin_before'],after_output=inp['flagged_output'])
    ob=next(o for o in state['obligations'] if o['priority']=='P0')
    append_review(inp['origin_review'],campaign_output=inp['origin_campaign'],
                  before_output=inp['origin_before'],after_output=inp['flagged_output'],
                  obligation_id=ob['id'],action='dispute',actor='independent-reviewer',
                  note='Newly disputed source evidence; closure must be reconsidered')
    new=assess(inp)
    assert new['cases'][0]['status']=='review_required'
    assert new['inputs']['origin_review_sha256']!=old['inputs']['origin_review_sha256']
    with pytest.raises(ValueError,match='disagrees'):
        verify_assessment(old,**inp)


def test_published_assessment_fails_verification_when_review_evolves(tmp_path):
    inp=make(tmp_path);out=tmp_path/'published';publish_assessment(assess(inp),out,**inp)
    journal=verify_review_publication(inp['origin_review'],campaign_output=inp['origin_campaign'],
                                      before_output=inp['origin_before'],after_output=inp['flagged_output'])
    gate=next(o for o in journal['obligations'] if o['kind']=='campaign_gate')
    append_review(inp['origin_review'],campaign_output=inp['origin_campaign'],
                  before_output=inp['origin_before'],after_output=inp['flagged_output'],
                  obligation_id=gate['id'],action='requires_action',actor='reviewer',
                  note='Supplemental review after initial closure candidate report')
    with pytest.raises(ValueError):verify_assessment_publication(out,**inp)


def test_concurrent_publication_uses_single_content_addressed_generation(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    inp=make(tmp_path);out=tmp_path/'pub';r=assess(inp)
    with ThreadPoolExecutor(max_workers=3) as executor:
        results=list(executor.map(lambda _:publish_assessment(r,out,**inp),range(3)))
    assert len(set(x['generation'] for x in results))==1
    assert verify_assessment_publication(out,**inp)['status']=='bounded_absence_candidates_require_human_closure'


def test_interrupted_pointer_commit_is_marked_failed(tmp_path,monkeypatch):
    import audit_engine.semantic_audit.ae06.publication as publication
    inp=make(tmp_path);out=tmp_path/'pub';r=assess(inp)
    original=publication._atomic_bytes;armed=[True]
    def inject(path,data):
        if armed[0] and str(path).endswith('LATEST.json') and b'"completed"' in data:
            armed[0]=False
            raise OSError('injected pointer commit failure')
        return original(path,data)
    monkeypatch.setattr(publication,'_atomic_bytes',inject)
    with pytest.raises(OSError,match='injected'):
        publish_assessment(r,out,**inp)
    assert json.loads((out/'LATEST.json').read_text())['status']=='failed'
    with pytest.raises(ValueError):verify_assessment_publication(out,**inp)


def test_symlinked_published_file_rejected_even_if_same_bytes(tmp_path):
    inp=make(tmp_path);out=tmp_path/'pub';rec=publish_assessment(assess(inp),out,**inp)
    f=out/'generations'/rec['generation']/'assessment.json'
    elsewhere=tmp_path/'identical.json';elsewhere.write_bytes(f.read_bytes())
    f.unlink();f.symlink_to(elsewhere)
    with pytest.raises(ValueError):verify_assessment_publication(out,**inp)


def test_unexpected_generation_member_rejected(tmp_path):
    inp=make(tmp_path);out=tmp_path/'pub';rec=publish_assessment(assess(inp),out,**inp)
    folder=out/'generations'/rec['generation']
    (folder/'surprise.txt').write_text('unsealed')
    with pytest.raises(ValueError,match='unexpected'):
        verify_assessment_publication(out,**inp)


def test_malformed_history_rejected(tmp_path):
    inp=make(tmp_path)
    with pytest.raises(ValueError,match='Cannot claim ordered'):
        assess({**inp,'history_campaigns':(inp['followup_campaign'],)})


def test_review_swapped_during_independent_verification_is_rejected(tmp_path,monkeypatch):
    import audit_engine.semantic_audit.ae06.service as service
    inp=make(tmp_path)
    original=service.read_verified_review
    def inject(path):
        record=copy.deepcopy(original(path))
        record['review_sha256']='0'*64
        return record
    monkeypatch.setattr(service,'read_verified_review',inject)
    with pytest.raises(ValueError,match='changed between'):
        assess(inp)


def test_deterministic_replay_and_ordering(tmp_path):
    inp=make(tmp_path,'different')
    first=assess(inp);second=assess(inp)
    assert canonical(first)==canonical(second)
    assert first['assessment_sha256']==second['assessment_sha256']
    assert [x['origin_finding_id'] for x in first['cases']] == sorted(
            x['origin_finding_id'] for x in first['cases'])
    assert len({x['case_id'] for x in first['cases']})==len(first['cases'])
    assert not first['assurance']['global_software_correctness_certified']
