"""AE-07 end-to-end tests use real sealed AE-01/04/05/06 publications.

Fixtures assert independent expected meaning; tests do not mock the verification
pipeline. Source, report and publication tampering are adversarial controls.
"""
from __future__ import annotations
import copy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from test_ae06_remediation import make
from audit_engine.semantic_audit.ae01.publication import canonical, sha
from audit_engine.semantic_audit.ae06 import build_assessment, publish_assessment
from audit_engine.semantic_audit.ae07 import (build_portfolio, verify_portfolio,
    publish_portfolio, verify_portfolio_publication, render_sarif)


def fixture(tmp_path, mode='repaired', review='requires_action', **kwargs):
    inp = make(tmp_path, mode, review=review, **kwargs)
    record = build_assessment(**inp)
    output = tmp_path/'ae06_assessment'
    publish_assessment(record, output, **inp)
    return {'assessment_output':str(output), 'inputs':{k:str(v) for k,v in inp.items()}}


def test_candidate_coverage_requires_human_review(tmp_path):
    row = fixture(tmp_path)
    report = build_portfolio([row])
    assert report['gate']['status']=='human_review_required'
    assert not report['gate']['release_authorized']
    assert not report['gate']['whole_repository_correctness_certified']
    assert any(t['kind']=='remediation_review' and t['priority']=='P2' for t in report['review_tasks'])
    assert verify_portfolio(report,[row])['verified_from_native_evidence']
    assert render_sarif(report)['runs'][0]['results']==[]


@pytest.mark.parametrize('mode,expected',[
    ('persistent','blocked_verified_policy_violations'),
    ('different','blocked_verified_policy_violations'),
    ('comment_only','blocked_verified_policy_violations'),
    ('new_unrelated','blocked_verified_policy_violations'),
    ('empty','inconclusive_required_coverage'),
    ('missing','inconclusive_required_coverage'),
    ('unknown','inconclusive_required_coverage'),
])
def test_violation_and_incomplete_are_not_clean(tmp_path,mode,expected):
    row=fixture(tmp_path,mode)
    result=build_portfolio([row])
    assert result['gate']['status']==expected
    assert not result['gate']['release_authorized']
    if expected.startswith('blocked'):
        assert len(render_sarif(result)['runs'][0]['results'])>=1
        findings=[t for t in result['review_tasks'] if t['kind']=='verified_finding']
        assert all(t['source_sha256'] and t['line'] >= 1 for t in findings)
    else:
        assert result['gate']['required_coverage_incomplete']


def test_unauthenticated_or_disputed_review_does_not_clear(tmp_path):
    row=fixture(tmp_path,review='dispute')
    report=build_portfolio([row])
    assert report['gate']['status']=='inconclusive_required_coverage'
    assert report['review_tasks'][0]['priority']=='P1'


def test_multi_assessment_different_generation_is_incomparable(tmp_path):
    (tmp_path/'one').mkdir()
    a=fixture(tmp_path/'one')
    (tmp_path/'two').mkdir()
    b=fixture(tmp_path/'two','empty')
    report=build_portfolio([a,b])
    assert report['gate']['status']=='inconclusive_incomparable_source_or_policy'
    assert report['scope']['distinct_generations']==2
    assert not report['scope']['comparable_current_source_and_policy']
    assert len(report['inputs'])==2
    assert canonical(build_portfolio([a,b]))==canonical(build_portfolio([b,a]))


def test_multi_assessment_current_violations_block_even_if_incomparable(tmp_path):
    (tmp_path/'one').mkdir(); (tmp_path/'two').mkdir()
    a=fixture(tmp_path/'one','persistent')
    b=fixture(tmp_path/'two')
    report=build_portfolio([a,b])
    assert report['gate']['status']=='blocked_verified_policy_violations'
    assert report['scope']['comparable_current_source_and_policy'] is False


def test_same_generation_with_two_independently_verified_ae06_publications(tmp_path):
    a=fixture(tmp_path)
    from audit_engine.semantic_audit.ae06.publication import _stored
    inputs=a['inputs']
    record=_stored(Path(a['assessment_output']))
    second=tmp_path/'second_ae06'
    publish_assessment(record,second,**inputs)
    b={'assessment_output':str(second),'inputs':inputs}
    report=build_portfolio([a,b])
    assert report['scope']['distinct_generations']==1
    assert report['gate']['status']=='human_review_required'
    assert len(report['review_tasks'])==1  # same original finding and source


def test_sarif_source_witnesses_only_verified_findings(tmp_path):
    row=fixture(tmp_path,'persistent')
    report=build_portfolio([row])
    sarif=render_sarif(report)
    assert sarif['version']=='2.1.0'
    assert sarif['runs'][0]['properties']['releaseAuthorized'] is False
    r=sarif['runs'][0]['results'][0]
    assert r['locations'][0]['physicalLocation']['artifactLocation']['uri']=='prod.py'
    assert r['locations'][0]['physicalLocation']['region']['startLine']==1
    assert r['partialFingerprints']['sourceSHA256']==next(t['source_sha256'] for t in report['review_tasks'] if t['kind']=='verified_finding')
    assert 'architecture' in r['ruleId']


def test_publication_and_detached_replay(tmp_path):
    row=fixture(tmp_path)
    out=tmp_path/'ae07_out'
    record=build_portfolio([row])
    receipt=publish_portfolio(record,out,entries=[row])
    assert receipt['generation'].startswith('ae07-')
    checked=verify_portfolio_publication(out,entries=[row])
    assert checked['portfolio_sha256']==record['portfolio_sha256']
    assert checked['sarif_results']==0
    assert publish_portfolio(record,out,entries=[row])['generation']==receipt['generation']


def test_tamper_portfolio_bytes_fail(tmp_path):
    row=fixture(tmp_path)
    out=tmp_path/'out'; receipt=publish_portfolio(build_portfolio([row]),out,entries=[row])
    f=out/'generations'/receipt['generation']/'portfolio.json'
    f.write_bytes(f.read_bytes()+b' ')
    with pytest.raises(ValueError): verify_portfolio_publication(out,entries=[row])


def test_tamper_sarif_even_if_valid_json_fail(tmp_path):
    row=fixture(tmp_path,'persistent')
    out=tmp_path/'out'; receipt=publish_portfolio(build_portfolio([row]),out,entries=[row])
    f=out/'generations'/receipt['generation']/'results.sarif'
    data=json.loads(f.read_bytes()); data['runs'][0]['results']=[]
    f.write_bytes(canonical(data))
    with pytest.raises(ValueError): verify_portfolio_publication(out,entries=[row])


def test_rehashed_forged_gate_rejected_by_independent_rederivation(tmp_path):
    row=fixture(tmp_path,'persistent')
    forged=copy.deepcopy(build_portfolio([row]))
    forged['gate']['status']='bounded_evidence_ready_for_human_review'
    forged['portfolio_sha256']=sha(canonical({k:v for k,v in forged.items() if k!='portfolio_sha256'}))
    with pytest.raises(ValueError,match='reverified'): verify_portfolio(forged,[row])


def test_rehashed_fake_review_task_rejected(tmp_path):
    row=fixture(tmp_path)
    record=copy.deepcopy(build_portfolio([row]))
    record['review_tasks']=[]
    record['portfolio_sha256']=sha(canonical({k:v for k,v in record.items() if k!='portfolio_sha256'}))
    with pytest.raises(ValueError,match='reverified'): verify_portfolio(record,[row])


def test_failed_publish_invalidates_previous_success(tmp_path):
    row=fixture(tmp_path)
    out=tmp_path/'out'; record=build_portfolio([row])
    publish_portfolio(record,out,entries=[row])
    forged=copy.deepcopy(record); forged['gate']['status']='forged'
    with pytest.raises(ValueError):publish_portfolio(forged,out,entries=[row])
    assert json.loads((out/'LATEST.json').read_bytes())['status']=='failed'
    with pytest.raises(ValueError,match='LATEST'):verify_portfolio_publication(out,entries=[row])


def test_source_publication_tamper_detected(tmp_path):
    row=fixture(tmp_path)
    from audit_engine.semantic_audit.ae06.publication import _stored
    out=Path(row['assessment_output']); latest=json.loads((out/'LATEST.json').read_bytes())
    f=out/'generations'/latest['generation']/'assessment.json'
    f.write_text(f.read_text()+'\n')
    with pytest.raises(ValueError):build_portfolio([row])


def test_ae01_source_evidence_tamper_detected(tmp_path):
    row=fixture(tmp_path)
    p=Path(row['inputs']['current_output']); last=json.loads((p/'LATEST.json').read_bytes())
    f=p/'generations'/last['generation']/'manifest.json'
    f.write_text('{}')
    with pytest.raises(ValueError):build_portfolio([row])


def test_review_journal_tamper_detected_by_native_replay(tmp_path):
    row=fixture(tmp_path)
    journal=Path(row['inputs']['origin_review'])
    (journal/'LATEST.json').write_text('{"status":"completed","generation":"invalid"}')
    with pytest.raises(ValueError):build_portfolio([row])


def test_same_assessment_duplicate_input_rejected(tmp_path):
    row=fixture(tmp_path)
    with pytest.raises(ValueError,match='Duplicate'):build_portfolio([row,row])


@pytest.mark.parametrize('bad', [[],[{}], [dict(assessment_output='a',inputs={})],
                                [{'assessment_output':'a','inputs':{k:'b' for k in ('origin_before','flagged_output','current_output','origin_campaign','origin_review','followup_campaign')},'extra':1}]])
def test_malformed_input_registry_rejected(bad):
    with pytest.raises(ValueError):build_portfolio(bad)


def test_symlink_output_rejected(tmp_path):
    row=fixture(tmp_path)
    real=tmp_path/'real'; real.mkdir(); link=tmp_path/'alias'; link.symlink_to(real,target_is_directory=True)
    with pytest.raises((ValueError,OSError)):
        publish_portfolio(build_portfolio([row]),link,entries=[row])


def test_source_output_overlap_rejected(tmp_path):
    row=fixture(tmp_path)
    with pytest.raises(ValueError,match='overlap'):
        publish_portfolio(build_portfolio([row]),Path(row['assessment_output'])/'nested',entries=[row])


def test_cli_errors_for_bad_manifest(tmp_path):
    manifest=tmp_path/'manifest.json'; manifest.write_text('{"entries":[]}')
    proc=subprocess.run([sys.executable,'-m','audit_engine.semantic_audit.ae07',
                         'publish','--manifest',str(manifest),'--output',str(tmp_path/'out')],
                        capture_output=True,text=True,timeout=20)
    assert proc.returncode==4 and 'AE-07 error' in proc.stderr


def test_cli_end_to_end_success_but_requires_review_exit3(tmp_path):
    row=fixture(tmp_path)
    manifest=tmp_path/'manifest.json'; manifest.write_bytes(canonical({'entries':[row]}))
    command=[sys.executable,'-m','audit_engine.semantic_audit.ae07']
    options=['--manifest',str(manifest),'--output',str(tmp_path/'out')]
    a=subprocess.run([*command,'publish',*options],capture_output=True,text=True,timeout=30)
    assert a.returncode==3, a.stderr
    b=subprocess.run([*command,'verify',*options],capture_output=True,text=True,timeout=30)
    assert b.returncode==3, b.stderr
    assert json.loads(a.stdout)['portfolio_sha256']==json.loads(b.stdout)['portfolio_sha256']



def test_publication_rejects_symlinked_sarif(tmp_path):
    row=fixture(tmp_path,'persistent')
    out=tmp_path/'out'; receipt=publish_portfolio(build_portfolio([row]),out,entries=[row])
    f=out/'generations'/receipt['generation']/'results.sarif'
    payload=tmp_path/'external.sarif'; payload.write_bytes(f.read_bytes())
    f.unlink(); f.symlink_to(payload)
    with pytest.raises(ValueError): verify_portfolio_publication(out,entries=[row])


def test_historical_generation_fails_closed_if_modified(tmp_path):
    row=fixture(tmp_path)
    out=tmp_path/'out'; record=build_portfolio([row])
    receipt=publish_portfolio(record,out,entries=[row])
    path=out/'generations'/receipt['generation']/'SEAL.json'
    path.write_text('{}')
    with pytest.raises(ValueError):publish_portfolio(record,out,entries=[row])
    assert json.loads((out/'LATEST.json').read_bytes())['status']=='failed'


def test_interrupted_publication_remains_noncurrent(tmp_path,monkeypatch):
    row=fixture(tmp_path)
    out=tmp_path/'out'; record=build_portfolio([row])
    import audit_engine.semantic_audit.ae07.publication as module
    original=module._atomic_bytes
    def fail_on_seal(path,data):
        if Path(path).name=='SEAL.json':
            raise OSError('injected disk error')
        return original(path,data)
    monkeypatch.setattr(module,'_atomic_bytes',fail_on_seal)
    with pytest.raises(OSError, match='injected disk error'):
        publish_portfolio(record,out,entries=[row])
    assert json.loads((out/'LATEST.json').read_bytes())['status']=='failed'
    with pytest.raises(ValueError):verify_portfolio_publication(out,entries=[row])


def test_concurrent_publication_serializes_without_corruption(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    row=fixture(tmp_path)
    out=tmp_path/'out'; record=build_portfolio([row])
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(publish_portfolio,record,out,entries=[row]) for _ in range(2)]
        receipts=[f.result(timeout=30) for f in futures]
    assert receipts[0]['generation']==receipts[1]['generation']
    assert verify_portfolio_publication(out,entries=[row])['verified_from_native_evidence']


def test_audit_classification_change_never_counts_as_clear(tmp_path):
    from test_ae06_remediation import LIFE
    row=fixture(tmp_path,current_life={**LIFE,'exp':'stable'})
    report=build_portfolio([row])
    assert report['gate']['status']=='inconclusive_required_coverage'
    assert report['review_tasks'][0]['priority']=='P1'


def test_no_reviewer_authentication_or_release_approval_in_sarif(tmp_path):
    row=fixture(tmp_path,'persistent')
    report=build_portfolio([row])
    sarif=render_sarif(report)
    assert report['gate']['reviewer_identity_authenticated'] is False
    assert sarif['runs'][0]['properties']['releaseAuthorized'] is False
    assert all(x['ruleId'] for x in sarif['runs'][0]['results'])
