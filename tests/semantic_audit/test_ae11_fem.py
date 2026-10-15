"""Independent arithmetic oracles and adversarial AE-11 integration tests."""
from __future__ import annotations
import copy
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from audit_engine.semantic_audit.ae01.publication import canonical, sha
from audit_engine.semantic_audit.ae11.numerics import build_report, verify_report
from audit_engine.semantic_audit.ae11.publication import publish, verify_publication

FIXTURE=Path(__file__).resolve().parents[1]/'fixtures'/'ae11'

@pytest.fixture
def case(tmp_path):
    root=tmp_path/'source';root.mkdir()
    spec=json.loads((FIXTURE/'spec.json').read_text())
    data=json.loads((FIXTURE/'bar_problem.json').read_text())
    return root,spec,data

def write_case(case):
    root,spec,data=case
    raw=(json.dumps(data,sort_keys=True,separators=(',',':'))+'\n').encode()
    (root/'bar_problem.json').write_bytes(raw)
    spec['artifact']['sha256']=hashlib.sha256(raw).hexdigest()
    spec_path=root/'spec.json'
    spec_path.write_text(json.dumps(spec,sort_keys=True))
    return spec_path,root

def statuses(report):
    return {x['id']:x['status'] for x in report['checks']}

def test_reference_fixture_and_exact_graph():
    report=build_report(FIXTURE/'spec.json',FIXTURE)
    assert report['verdict']=='consistent_within_declared_checks'
    assert len(report['checks'])==7
    assert set(statuses(report).values())=={'consistent'}
    assert report['graph']['nodes']
    assert verify_report(report,FIXTURE/'spec.json',FIXTURE)['checks']==7

def test_independent_bar_equilibrium_oracle():
    data=json.loads((FIXTURE/'bar_problem.json').read_text())
    K=data['model']['stiffness'];u=data['model']['displacements'];f=data['model']['loads']
    # This expected analytic solution is independent of the auditor's output:
    # a unit spring at each bar segment, end force 1, left fixed.
    assert u==['0','1','2']
    assert [sum(int(K[i][j])*int(u[j]) for j in range(3)) for i in range(3)]==[-1,0,1]
    assert f==['0','0','1']
    assert data['model']['strain_energy']=='1'

@pytest.mark.parametrize('modify,check',[
 (lambda d:d['model']['stiffness'][0].__setitem__(1,'-0.8'),'matrix_symmetry'),
 (lambda d:d['model']['loads'].__setitem__(2,'1.1'),'free_equilibrium_residual'),
 (lambda d:d['model']['fixed_values'].__setitem__('0','0.1'),'dirichlet_displacement'),
 (lambda d:d['model']['stiffness'][2].__setitem__(2,'0.1'),'constrained_positive_definiteness'),
 (lambda d:d['model'].__setitem__('strain_energy','1.05'),'strain_energy'),
 (lambda d:d['refinements'][2].__setitem__('error','.2'),'refinement_error_monotonicity'),
 (lambda d:[x.__setitem__('error',str(v)) for x,v in zip(d['refinements'],['.5','.25','.125','.0625'])], 'observed_refinement_order'),
])
def test_independent_known_defects(case,modify,check):
    modify(case[2]);spec,root=write_case(case)
    report=build_report(spec,root)
    assert report['verdict']=='inconsistent'
    assert statuses(report)[check]=='inconsistent'

@pytest.mark.parametrize('mutator',[
 lambda d:d['model'].__setitem__('degrees_of_freedom',4),
 lambda d:d['model']['stiffness'].__setitem__(0,['0']),
 lambda d:d['model'].__setitem__('assumptions',['linear_static']),
 lambda d:d['model']['units'].__setitem__('force','kg'),
 lambda d:d['model']['fixed_values'].__setitem__('9','0'),
 lambda d:d['model'].__setitem__('fixed_values',{}),
 lambda d:d.__setitem__('refinements',d['refinements'][:2]),
 lambda d:d['refinements'][1].__setitem__('h','.8'),
 lambda d:d['refinements'][1].__setitem__('error','0'),
 lambda d:d['model']['loads'].__setitem__(1,'NaN'),
 lambda d:d['model']['loads'].__setitem__(1,1.5),
 lambda d:d['model']['stiffness'][0].__setitem__(0,'Infinity'),
])
def test_unsupported_or_malformed_data_inconclusive(case,mutator):
    mutator(case[2]);spec,root=write_case(case)
    result=build_report(spec,root)
    assert result['verdict']=='inconclusive'
    assert result['artifact']['status']=='unassessed'
    assert not result['checks']

@pytest.mark.parametrize('key',[
 'symmetry_abs','residual_abs','fixed_abs','positive_pivot_min','energy_abs','order_min','error_monotonic_abs'
])
def test_negative_threshold_rejected(case,key):
    case[1]['checks'][key]='-1'
    spec,root=write_case(case)
    with pytest.raises(ValueError,match='Negative'):
        build_report(spec,root)

def test_source_tampering_rejected(case):
    spec,root=write_case(case)
    valid=build_report(spec,root)
    raw=(root/'bar_problem.json').read_bytes()
    (root/'bar_problem.json').write_bytes(raw+b' ')
    observed=build_report(spec,root)
    assert observed['verdict']=='inconclusive'
    assert observed['artifact']['status']=='hash_mismatch'
    with pytest.raises(ValueError):verify_report(valid,spec,root)

def test_precision_is_not_binary_float(case):
    # Report tiny but representable deviation; should not round to zero.
    case[2]['model']['loads'][2]='1.00000000000000000000000000000000000001'
    case[1]['checks']['residual_abs']='0'
    spec,root=write_case(case)
    result=build_report(spec,root)
    assert statuses(result)['free_equilibrium_residual']=='inconsistent'

def test_forged_report_digest_rejected():
    report=build_report(FIXTURE/'spec.json',FIXTURE)
    report['checks'][0]['status']='inconsistent'
    report['record_sha256']=sha(canonical({k:v for k,v in report.items() if k!='record_sha256'}))
    with pytest.raises(ValueError,match='changed'):
        verify_report(report,FIXTURE/'spec.json',FIXTURE)

def test_deterministic_and_repeated_publication(tmp_path):
    output=tmp_path/'output'
    first=publish(FIXTURE/'spec.json',FIXTURE,output)
    second=publish(FIXTURE/'spec.json',FIXTURE,output)
    assert first==second==verify_publication(output,FIXTURE/'spec.json',FIXTURE)
    assert len(list((output/'generations').iterdir()))==1

def test_corrupt_published_report_rejected(tmp_path):
    out=tmp_path/'out';publish(FIXTURE/'spec.json',FIXTURE,out)
    gen=next((out/'generations').iterdir())
    (gen/'report.json').write_bytes(b'{}')
    with pytest.raises(ValueError):verify_publication(out,FIXTURE/'spec.json',FIXTURE)

def test_pointer_tampering_rejected(tmp_path):
    out=tmp_path/'out';publish(FIXTURE/'spec.json',FIXTURE,out)
    pointer=json.loads((out/'LATEST.json').read_text());pointer['seal_sha256']='0'*64
    (out/'LATEST.json').write_text(json.dumps(pointer))
    with pytest.raises(ValueError):verify_publication(out,FIXTURE/'spec.json',FIXTURE)

def test_safe_recovery_after_bad_input(case,tmp_path):
    spec,root=write_case(case);out=tmp_path/'out';publish(spec,root,out)
    case[1]['checks']['residual_abs']='-1';spec,root=write_case(case)
    with pytest.raises(ValueError):publish(spec,root,out)
    assert json.loads((out/'LATEST.json').read_text())['status']=='failed'
    with pytest.raises(ValueError):verify_publication(out,spec,root)

def test_source_symlink_outside_root_rejected(case,tmp_path):
    spec,root=write_case(case)
    outside=tmp_path/'outside.json';outside.write_bytes((root/'bar_problem.json').read_bytes())
    (root/'bar_problem.json').unlink();(root/'bar_problem.json').symlink_to(outside)
    result=build_report(spec,root)
    assert result['verdict']=='inconclusive'

def test_output_symlink_rejected(tmp_path):
    target=tmp_path/'target';target.mkdir()
    out=tmp_path/'out';out.symlink_to(target,target_is_directory=True)
    with pytest.raises(ValueError):publish(FIXTURE/'spec.json',FIXTURE,out)

def test_cli_run_verify(tmp_path):
    output=tmp_path/'cli'
    for command in ('run','verify'):
        cp=subprocess.run([sys.executable,'-m','audit_engine.semantic_audit.ae11',command,
                           '--spec',str(FIXTURE/'spec.json'),'--artifacts-root',str(FIXTURE),
                           '--output',str(output)],capture_output=True,text=True,timeout=20)
        assert cp.returncode==0,cp.stderr
        assert json.loads(cp.stdout)['checks']==7

def test_no_false_complete_after_error(case):
    spec,root=write_case(case)
    case[2]['model']['loads']=['0']
    spec,root=write_case(case)
    result=build_report(spec,root)
    assert not result['checks']
    assert result['verdict']=='inconclusive'
