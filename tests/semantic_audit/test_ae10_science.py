"""Independent oracles: expectations are independent of produced report status."""
import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from audit_engine.semantic_audit.ae10 import (build_report, verify_report,
                                               publish_scientific_audit, verify_publication)
from audit_engine.semantic_audit.ae01.publication import canonical, sha

FIXTURE=Path(__file__).resolve().parents[1]/'fixtures/ae10'


def setup(tmp_path):
    data=tmp_path/'input';data.mkdir()
    artifact=data/'experiment.json';artifact.write_bytes((FIXTURE/'experiment.json').read_bytes())
    for f in FIXTURE.glob('statement_*.txt'):
        (data/f.name).write_bytes(f.read_bytes())
    spec=json.loads((FIXTURE/'spec.json').read_text())
    spec_file=tmp_path/'policy.json';spec_file.write_text(json.dumps(spec,sort_keys=True))
    return data,spec_file,spec,artifact


def write_spec(path,spec):path.write_text(json.dumps(spec,sort_keys=True))


def seed(spec,aid='experiment'):
    return next(x for x in spec['artifacts'] if x['id']==aid)


def update_digest(spec,artifact):
    seed(spec)['sha256']=hashlib.sha256(artifact.read_bytes()).hexdigest()


def change_measurement(artifact,value=None,unit=None,key='modulus'):
    obj=json.loads(artifact.read_text())
    if value is not None:obj['data'][key]['value']=value
    if unit is not None:obj['data'][key]['unit']=unit
    artifact.write_text(json.dumps(obj,sort_keys=True))


def assert_claim(report,claim_id,check_id,status):
    row=next(c for c in report['claims'] if c['id']==claim_id)
    check=next(c for c in row['checks'] if c['id']==check_id)
    assert check['status']==status
    return check


def test_actual_semantic_graph_and_scientific_g3_policy(tmp_path):
    data,p,_,_=setup(tmp_path)
    report=build_report(p,data)
    assert report['verdict']=='consistent_within_declared_checks'
    assert len(report['graph']['edges'])==2
    assert {(e['source'],e['target'],e['relation']) for e in report['graph']['edges']}=={
        ('claim:elastic_modulus','evidence:experiment','SUPPORTED_BY'),
        ('claim:displacement_limit','evidence:experiment','SUPPORTED_BY')}
    assert len(report['g3_scientific_support_executions'])==2
    for r in report['g3_scientific_support_executions']:
        x=r['execution']
        assert x['reason']=='executed'
        assert len(x['obligations'])==len(x['receipts'])==1
        assert not x['findings']
    assert_claim(report,'elastic_modulus','check_modulus','consistent')
    assert_claim(report,'displacement_limit','check_disp','consistent')
    assert verify_report(report,p,data)['verified_claims']==2


def test_g3_rule_detects_declared_missing_support(tmp_path):
    data,p,spec,_=setup(tmp_path)
    spec['claims'][0]['supports']=[]
    spec['claims'][0]['checks']=[]
    write_spec(p,spec)
    r=build_report(p,data)
    assert r['verdict']=='inconclusive'
    x=next(v['execution'] for v in r['g3_scientific_support_executions'] if v['claim_id']=='elastic_modulus')
    assert len(x['findings'])==1
    assert x['receipts'][0]['evidence_state']=='validated'


@pytest.mark.parametrize('value,status', [('209.5','consistent'),('210.5','consistent'),
 ('210.50000000001','inconsistent'),('209.49999999999','inconsistent'), ('100.0','inconsistent')])
def test_decimal_boundary_exactness(tmp_path,value,status):
    data,p,spec,artifact=setup(tmp_path)
    change_measurement(artifact,value=value)
    update_digest(spec,artifact);write_spec(p,spec)
    assert_claim(build_report(p,data),'elastic_modulus','check_modulus',status)


@pytest.mark.parametrize('op,expected,value,tolerance,status', [
 ('eq','3.00','3.00001','0.00001','consistent'),
 ('eq','3.00','3.00002','0.00001','inconsistent'),
 ('ge','3.00','2.99','0.01','consistent'),
 ('ge','3.00','2.989','0.01','inconsistent'),
 ('le','3.00','3.01','0.01','consistent'),
 ('le','3.00','3.011','0.01','inconsistent'),
])
def test_comparison_operator_oracles(tmp_path,op,expected,value,tolerance,status):
    data,p,spec,artifact=setup(tmp_path)
    k=spec['claims'][0]['checks'][0]
    k.update(op=op,expected=expected,tolerance=tolerance)
    change_measurement(artifact,value=value)
    update_digest(spec,artifact);write_spec(p,spec)
    assert_claim(build_report(p,data),'elastic_modulus','check_modulus',status)


def test_high_precision_numbers_do_not_round_away_a_discrepancy(tmp_path):
    data,p,spec,artifact=setup(tmp_path)
    # A 60-digit integer plus a fractional perturbation is a valid decimal
    # observation; default Decimal precision 28 would round this subtraction.
    expected='9'*60 + '.000000'
    observed='9'*60 + '.000001'
    k=spec['claims'][0]['checks'][0]
    k.update(op='eq', expected=expected, tolerance='0')
    change_measurement(artifact,value=observed)
    update_digest(spec,artifact);write_spec(p,spec)
    assert_claim(build_report(p,data),'elastic_modulus','check_modulus','inconsistent')


def test_unit_disagreement_does_not_convert(tmp_path):
    data,p,spec,artifact=setup(tmp_path)
    change_measurement(artifact,unit='MPa')
    update_digest(spec,artifact);write_spec(p,spec)
    report=build_report(p,data)
    assert report['verdict']=='inconclusive'
    assert_claim(report,'elastic_modulus','check_modulus','unassessed')


def test_missing_measurement_field_is_unassessed(tmp_path):
    data,p,spec,artifact=setup(tmp_path)
    o=json.loads(artifact.read_text());del o['data']['modulus'];artifact.write_text(json.dumps(o))
    update_digest(spec,artifact);write_spec(p,spec)
    assert build_report(p,data)['verdict']=='inconclusive'


def test_evidence_edit_without_digest_update_is_fail_closed(tmp_path):
    data,p,_,artifact=setup(tmp_path)
    r=build_report(p,data)
    change_measurement(artifact,value='1')
    now=build_report(p,data)
    assert now['verdict']=='inconclusive'
    assert now['artifacts'][0]['status']=='hash_mismatch'
    with pytest.raises(ValueError):verify_report(r,p,data)


def test_structural_support_with_no_checks_is_not_scientific_validation(tmp_path):
    data,p,spec,_=setup(tmp_path)
    spec['claims'][0]['checks']=[];write_spec(p,spec)
    assert build_report(p,data)['verdict']=='inconclusive'


def test_source_missing_is_incomplete_not_unsupported(tmp_path):
    data,p,_,a=setup(tmp_path)
    a.unlink()
    r=build_report(p,data)
    assert r['artifacts'][0]['status']=='unavailable'
    assert r['verdict']=='inconclusive'
    assert not any(x['execution']['findings'] for x in r['g3_scientific_support_executions'])


@pytest.mark.parametrize('alter', [
 lambda s:s['claims'].append(copy.deepcopy(s['claims'][0])),
 lambda s:s['artifacts'].append(copy.deepcopy(s['artifacts'][0])),
 lambda s:s['claims'][0]['supports'].append('unknown'),
 lambda s:s['claims'][0]['checks'][0].update(tolerance='-0.01'),
 lambda s:s['claims'][0]['checks'][0].update(op='eval'),
 lambda s:s['claims'][0]['checks'][0].update(expected=['3','2'],op='between'),
 lambda s:s['claims'][0]['checks'][0].update(artifact='other'),
 lambda s:s['claims'][0]['checks'][0].update(expected='NaN'),
 lambda s:s['artifacts'][0].update(path='../escape'),
 lambda s:s['artifacts'][0].update(path='/tmp/escape'),
 lambda s:s['artifacts'][0].update(path='dir\\escape'),
])
def test_invalid_spec_rejected(tmp_path,alter):
    data,p,spec,_=setup(tmp_path)
    alter(spec);write_spec(p,spec)
    with pytest.raises((ValueError,TypeError,KeyError)):build_report(p,data)


def test_reject_json_member_duplicates(tmp_path):
    data,p,_,_=setup(tmp_path)
    p.write_text('{"schema":"ae10/scientific-spec/v1","schema":"x","artifacts":[],"claims":[]}')
    with pytest.raises(ValueError,match='Duplicate'):build_report(p,data)


def test_out_of_scope_symlink_file(tmp_path):
    data,p,spec,artifact=setup(tmp_path)
    other=tmp_path/'outside.json';other.write_bytes(artifact.read_bytes())
    artifact.unlink();artifact.symlink_to(other)
    assert build_report(p,data)['verdict']=='inconclusive'


def test_nested_symlink_directory(tmp_path):
    data,p,spec,artifact=setup(tmp_path)
    another=tmp_path/'external';another.mkdir();(another/'experiment.json').write_bytes(artifact.read_bytes())
    (data/'sub').symlink_to(another,target_is_directory=True)
    seed(spec)['path']='sub/experiment.json';write_spec(p,spec)
    assert build_report(p,data)['verdict']=='inconclusive'


def test_recomputed_forged_verdict_is_rejected_by_source_replay(tmp_path):
    data,p,_,_=setup(tmp_path)
    r=build_report(p,data)
    r['claims'][0]['checks'][0]['status']='inconsistent'
    r['verdict']='inconsistent'
    r['record_sha256']=sha(canonical({k:v for k,v in r.items() if k!='record_sha256'}))
    with pytest.raises(ValueError,match='disagrees'):verify_report(r,p,data)


def test_tampered_graph_with_resealed_top_level_rejected(tmp_path):
    data,p,_,_=setup(tmp_path)
    r=build_report(p,data)
    r['graph']['edges'].clear()
    r['record_sha256']=sha(canonical({k:v for k,v in r.items() if k!='record_sha256'}))
    with pytest.raises(ValueError):verify_report(r,p,data)


def test_claim_statement_source_edit_invalidates_report(tmp_path):
    data,p,_,_=setup(tmp_path)
    r=build_report(p,data)
    (data/'statement_elastic_modulus.txt').write_text('A different scientific claim\n')
    now=build_report(p,data)
    assert now['verdict']=='inconclusive'
    assert now['claims'][1]['statement_status']=='hash_mismatch' or now['claims'][0]['statement_status']=='hash_mismatch'
    with pytest.raises(ValueError):verify_report(r,p,data)


def test_source_spec_mutation_invalidates_previous_run(tmp_path):
    data,p,spec,_=setup(tmp_path)
    r=build_report(p,data)
    spec['claims'][0]['statement_sha256']='a'*64;write_spec(p,spec)
    with pytest.raises(ValueError):verify_report(r,p,data)


def test_published_generation_and_detached_verification(tmp_path):
    data,p,_,_=setup(tmp_path)
    out=tmp_path/'published'
    a=publish_scientific_audit(p,data,out)
    assert a['verdict']=='consistent_within_declared_checks'
    assert a==verify_publication(out,p,data)
    assert len(list((out/'generations').iterdir()))==1
    assert publish_scientific_audit(p,data,out)==a


def test_published_artifact_tampering_detected(tmp_path):
    data,p,_,_=setup(tmp_path)
    out=tmp_path/'published';publish_scientific_audit(p,data,out)
    gen=next((out/'generations').iterdir())
    report=json.loads((gen/'report.json').read_text());report['verdict']='inconsistent'
    (gen/'report.json').write_bytes(canonical(report))
    with pytest.raises(ValueError):verify_publication(out,p,data)


def test_publication_failure_invalidates_previous_success(tmp_path):
    data,p,_,_=setup(tmp_path)
    out=tmp_path/'published';publish_scientific_audit(p,data,out)
    # The next run encounters an invalid source scope but must not expose old LATEST.
    p.write_text('{}')
    with pytest.raises(ValueError):publish_scientific_audit(p,data,out)
    assert json.loads((out/'LATEST.json').read_text())['status']=='failed'
    with pytest.raises(ValueError):verify_publication(out,p,data)


def test_publication_rejects_symlinked_outputs(tmp_path):
    data,p,_,_=setup(tmp_path)
    other=tmp_path/'outside';other.mkdir()
    (tmp_path/'linked').symlink_to(other, target_is_directory=True)
    with pytest.raises(ValueError):publish_scientific_audit(p,data,tmp_path/'linked')


def test_publication_rejects_output_overlapping_input(tmp_path):
    data,p,_,_=setup(tmp_path)
    with pytest.raises(ValueError):publish_scientific_audit(p,data,data/'results')


def test_cli_run_and_verify(tmp_path):
    data,p,_,_=setup(tmp_path)
    out=tmp_path/'publication'
    root=Path(__file__).resolve().parents[2]
    for action in ('run','verify'):
        result=subprocess.run([sys.executable,'-m','audit_engine.semantic_audit.ae10',action,'--spec',str(p),
          '--artifacts-root',str(data),'--output',str(out)],cwd=root,capture_output=True,text=True)
        assert result.returncode==0,result.stderr
        assert json.loads(result.stdout)['verdict']=='consistent_within_declared_checks'


def test_cli_inconclusive_exits_nonzero_without_crash(tmp_path):
    data,p,spec,_=setup(tmp_path)
    spec['claims'][0]['checks']=[];write_spec(p,spec)
    root=Path(__file__).resolve().parents[2]
    result=subprocess.run([sys.executable,'-m','audit_engine.semantic_audit.ae10','run','--spec',str(p),
     '--artifacts-root',str(data),'--output',str(tmp_path/'publication')],cwd=root,capture_output=True,text=True)
    assert result.returncode==2,result.stderr
    assert json.loads(result.stdout)['verdict']=='inconclusive'
