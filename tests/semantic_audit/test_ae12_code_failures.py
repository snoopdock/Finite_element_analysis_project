"""Independent acceptance cases for source-bound code-pattern auditing."""
from __future__ import annotations

from collections import Counter
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from audit_engine.semantic_audit.ae01.pipeline import audit_repository
from audit_engine.semantic_audit.ae01.publication import canonical,sha
from audit_engine.semantic_audit.ae12.analyze import build_report,verify_report,load_policy,_scan_file
from audit_engine.semantic_audit.ae12.publication import publish,verify_publication

BASE=Path(__file__).resolve().parents[2]
RULE=BASE/'specs/rules/architecture/no_production_to_experimental_dependency.yaml'
FIX=BASE/'tests/fixtures/ae12'
ALL_RULES=['mutable_default','swallowed_exception','bare_except','finally_return',
           'duplicate_dict_key','assert_call','subprocess_shell']

@pytest.fixture
def lab(tmp_path):
    root=tmp_path/'source'; pkg=root/'pkg';pkg.mkdir(parents=True)
    (pkg/'__init__.py').write_text('')
    (pkg/'risk_patterns.py').write_bytes((FIX/'risk_patterns.py').read_bytes())
    (pkg/'user.py').write_text('from .risk_patterns import shared\n')
    src=tmp_path/'ae01'
    a=audit_repository(root,src,lifecycle={'pkg':'stable','pkg.risk_patterns':'stable',
                 'pkg.user':'production'},policy_file=RULE)
    assert a['report']['assurance_completeness']=='complete_within_declared_scope'
    policy=tmp_path/'policy.json'
    policy.write_bytes((FIX/'policy.json').read_bytes())
    log=tmp_path/'error.txt'
    log.write_text('Traceback (most recent call last):\n'
                   '  File "/runner/src/pkg/risk_patterns.py", line 17, in suppresses_exception\n'
                   'RuntimeError: fixture\n')
    return root,src,policy,log,tmp_path/'ae12'


def test_oracle_exact_counts(lab):
    root,src,policy,log,_=lab
    report=build_report(src,root,policy)
    expected=json.loads((FIX/'expected.json').read_text())['risk_counts']
    assert Counter(h['rule'] for h in report['findings'])==expected
    assert report['assurance_status']=='bounded_observations'
    assert len(report['graph_analyses'])==1
    assert report['rule_coverage'] and report['source_coverage'][0]['status']=='scanned'
    assert report['conclusion'].endswith('not_verified_defects_or_root_causes')
    assert verify_report(report,src,root,policy)['verified']


def test_independent_runtime_behavior_oracle():
    # The expected behavior is checked by Python itself, not AE-12's AST matcher.
    spec=importlib.util.spec_from_file_location('ae12_control',FIX/'risk_patterns.py')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    assert mod.shared()==['again']
    assert mod.shared()==['again','again']
    assert mod.swallowed() is None
    assert mod.suppresses_exception()==1
    assert mod.overwrites_key()=={1:'second'}


@pytest.mark.parametrize('rule,source', [
 ('mutable_default','def f(x=[]): return x'),
 ('mutable_default','def f(*, data={}): return data'),
 ('mutable_default','def f(x=set()): return x'),
 ('swallowed_exception','try:\n pass\nexcept Exception:\n pass'),
 ('bare_except','try:\n pass\nexcept:\n print("ok")'),
 ('finally_return','def f():\n try:\n  raise KeyError\n finally:\n  return 7'),
 ('duplicate_dict_key','x={"a":1,"a":2}'),
 ('duplicate_dict_key','x={1:1, True:2}'),
 ('assert_call','assert check()'),
 ('subprocess_shell','subprocess.Popen("echo", shell=True)'),
])
def test_individual_positive_patterns(rule,source):
    hits=_scan_file('demo.py',source.encode(),'utf-8',set(ALL_RULES))
    assert any(h['rule']==rule for h in hits)
    assert all(h['source_sha256']==hashlib.sha256(source.encode()).hexdigest() for h in hits)


@pytest.mark.parametrize('source',[
 'def f(x=None): return x',
 'try:\n pass\nexcept Exception:\n raise',
 'def f():\n try:\n  return 2\n finally:\n  print("done")',
 'x={"one":1,"two":2}',
 'assert True',
 'subprocess.run("echo", shell=False)',
 'def f():\n def inner():\n  return 1\n try:\n  return 2\n finally:\n  pass',
])
def test_negative_controls(source):
    assert _scan_file('clean.py',source.encode(),'utf-8',set(ALL_RULES))==[]


def test_occurrence_identity_and_duplicate_default(lab):
    root,src,policy,_,_=lab
    report=build_report(src,root,policy)
    assert len({h['id'] for h in report['findings']})==len(report['findings'])
    assert report['source_digest'] and all(h['source_sha256'] for h in report['findings'])
    assert build_report(src,root,policy)==report


def test_runtime_correlation_is_noncausal(lab):
    root,src,policy,log,_=lab
    result=build_report(src,root,policy,runtime_log=log)
    assert result['runtime']['failure_signal_classes']==['RuntimeError']
    assert result['runtime']['observed_paths']==['pkg/risk_patterns.py']
    assert all(f['runtime_co_observed_module'] for f in result['findings'])
    assert result['conclusion'].endswith('not_verified_defects_or_root_causes')
    assert verify_report(result,src,root,policy,runtime_log=log)['verified']


def test_bad_runtime_log_is_inconclusive(lab):
    root,src,policy,log,_=lab
    log.write_text('failure without parseable frame')
    report=build_report(src,root,policy,runtime_log=log)
    assert report['assurance_status']=='inconclusive'
    assert 'runtime_correlation_inconclusive' in report['issues']


def test_missing_policy_file_not_clean(lab):
    root,src,policy,_,_=lab
    pol=json.loads(policy.read_text());pol['paths']=['pkg/missing.py']
    policy.write_text(json.dumps(pol))
    report=build_report(src,root,policy)
    assert report['assurance_status']=='inconclusive'
    assert report['source_coverage'][0]['status']=='not_audited'


@pytest.mark.parametrize('modify',[
 lambda p:p.update(schema='ae12/invalid'),
 lambda p:p.update(paths=['../secret.py']),
 lambda p:p.update(paths=['*','pkg/risk_patterns.py']),
 lambda p:p.update(rules=['fictional_rule']),
 lambda p:p.update(rules=['mutable_default','mutable_default']),
 lambda p:p.update(max_findings=0),
 lambda p:p.update(max_graph_modules=True),
])
def test_invalid_policy_rejected(lab,modify):
    root,src,policy,_,_=lab
    p=json.loads(policy.read_text());modify(p)
    policy.write_text(json.dumps(p))
    with pytest.raises(ValueError):build_report(src,root,policy)


def test_finding_budget_raises_incompleteness(lab):
    root,src,policy,_,_=lab
    p=json.loads(policy.read_text());p['max_findings']=1
    policy.write_text(json.dumps(p))
    result=build_report(src,root,policy)
    assert result['assurance_status']=='inconclusive'
    assert 'finding_budget_exceeded' in result['issues']


def test_current_source_change_rejected(lab):
    root,src,policy,_,_=lab
    report=build_report(src,root,policy)
    p=root/'pkg'/'risk_patterns.py'
    p.write_text(p.read_text()+'\n# edited\n')
    with pytest.raises(ValueError):verify_report(report,src,root,policy)


def test_policy_byte_edit_rejected(lab):
    root,src,policy,_,_=lab
    report=build_report(src,root,policy)
    policy.write_bytes(policy.read_bytes()+b'\n')
    with pytest.raises(ValueError):verify_report(report,src,root,policy)


def test_forged_report_with_self_consistent_digest_rejected(lab):
    root,src,policy,_,_=lab
    report=build_report(src,root,policy)
    report['findings'][0]['rule']='invented_rule'
    report['record_sha256']=sha(canonical({k:v for k,v in report.items() if k!='record_sha256'}))
    with pytest.raises(ValueError):verify_report(report,src,root,policy)


def test_published_generation_verified(lab):
    root,src,policy,_,out=lab
    res=publish(src,root,policy,out)
    assert res['verified']
    assert publish(src,root,policy,out)==res
    assert len(list((out/'generations').iterdir()))==1
    assert verify_publication(out,src,root,policy)['verified']


@pytest.mark.parametrize('filename',['report.json','SEAL.json'])
def test_publication_tampering_detected(lab,filename):
    root,src,policy,_,out=lab
    publish(src,root,policy,out)
    folder=next((out/'generations').iterdir())
    f=folder/filename;f.write_bytes(f.read_bytes()+b' ')
    with pytest.raises(ValueError):verify_publication(out,src,root,policy)


def test_failed_publication_does_not_leave_latest_success(lab):
    root,src,policy,_,out=lab
    publish(src,root,policy,out)
    policy.write_text('{not json')
    with pytest.raises(ValueError):publish(src,root,policy,out)
    assert json.loads((out/'LATEST.json').read_text())['status']=='failed'
    with pytest.raises(ValueError):verify_publication(out,src,root,policy)


def test_output_symlink_rejected(lab,tmp_path):
    root,src,policy,_,out=lab
    other=tmp_path/'elsewhere';other.mkdir()
    out.symlink_to(other, target_is_directory=True)
    with pytest.raises(ValueError):publish(src,root,policy,out)


def test_source_symlink_rejected(lab,tmp_path):
    root,src,policy,_,_=lab
    f=root/'pkg/risk_patterns.py';f.unlink()
    outside=tmp_path/'elsewhere.py';outside.write_text('print(1)')
    f.symlink_to(outside)
    with pytest.raises((ValueError,OSError)):build_report(src,root,policy)


def test_cli_published_and_verified(lab):
    root,src,policy,_,out=lab
    argv=[sys.executable,'-m','audit_engine.semantic_audit.ae12','--ae01-output',str(src),
          '--source-root',str(root),'--policy',str(policy),'--output',str(out)]
    assert subprocess.run(argv,capture_output=True,text=True,timeout=25).returncode==0
    assert subprocess.run(argv+['--verify'],capture_output=True,text=True,timeout=25).returncode==0
