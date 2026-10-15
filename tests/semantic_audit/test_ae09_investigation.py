"""Externally observable AE-09 source-to-log-to-graph acceptance controls."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from audit_engine.semantic_audit.ae01.pipeline import audit_repository
from audit_engine.semantic_audit.ae09.investigate import build_report,extract_events,verify_report,_match_path,_log_bytes
from audit_engine.semantic_audit.ae09.publication import publish_investigation,verify_publication

POLICY=Path(__file__).resolve().parents[2]/'specs/rules/architecture/no_production_to_experimental_dependency.yaml'

@pytest.fixture
def lab(tmp_path):
    src=tmp_path/'src';(src/'pkg').mkdir(parents=True)
    (src/'pkg'/'__init__.py').write_text('')
    (src/'pkg'/'boom.py').write_text('def explode():\n    raise ValueError("controlled fixture")\n')
    (src/'pkg'/'service.py').write_text('from .boom import explode\n\ndef run():\n    return explode()\n')
    (src/'pkg'/'caller.py').write_text('from .service import run\n')
    # Opposite-direction edge: should not be propagated as a dependent of boom.
    (src/'pkg'/'unrelated.py').write_text('x=1\n')
    audit=tmp_path/'ae01'
    result=audit_repository(src,audit,lifecycle={
        'pkg':'production','pkg.boom':'experimental','pkg.service':'production',
        'pkg.caller':'production','pkg.unrelated':'production'},policy_file=POLICY)
    assert result['report']['assurance_completeness']=='complete_within_declared_scope'
    assert result['report']['counts']['verified_findings']==1
    log=tmp_path/'workflow.txt'
    log.write_text('Traceback (most recent call last):\n'
                   '  File "/runner/src/pkg/boom.py", line 2, in explode\n'
                   '    raise ValueError("controlled fixture")\nValueError: controlled fixture\n')
    return src,audit,log,tmp_path/'ae09'


def test_real_source_graph_correlation(lab):
    src,audit,log,_=lab
    report=build_report(audit,log,src)
    assert report['assurance_status']=='bounded_correlation'
    assert report['issues']==[]
    assert report['conclusion']=='review_hypotheses_only_not_proven_root_cause'
    frame=report['observations'][0]
    assert (frame['source_path'],frame['source_line'],frame['match_strategy'])==('pkg/boom.py',2,'suffix')
    assert len(frame['source_line_sha256'])==64
    reached={row['module']:row for row in report['review_candidates']}
    assert reached['pkg.boom']['depth']==0
    assert reached['pkg.service']['depth']==1
    assert reached['pkg.caller']['depth']==2
    assert 'pkg.unrelated' not in reached
    assert all(row['import_occurrence_path'] for row in (reached['pkg.service'],reached['pkg.caller']))
    assert len(report['graph_analyses'])==1
    assert len(report['graph_analyses'][0]['analysis_id'])>10


def test_replay_and_publication(lab):
    src,audit,log,out=lab
    published=publish_investigation(audit,log,src,out)
    assert published['verified']
    assert verify_publication(out,audit,log,src)['review_candidates']==3
    assert publish_investigation(audit,log,src,out)['generation']==published['generation']
    assert len(list((out/'generations').iterdir()))==1

@pytest.mark.parametrize('member', ['report.json','SEAL.json'])
def test_modified_artifact_rejected(lab,member):
    src,audit,log,out=lab
    pub=publish_investigation(audit,log,src,out)
    path=out/'generations'/pub['generation']/member
    path.write_bytes(path.read_bytes()+b' ')
    with pytest.raises(ValueError):verify_publication(out,audit,log,src)


def test_resealed_forged_hypothesis_rejected(lab):
    from audit_engine.semantic_audit.ae01.publication import canonical,sha
    src,audit,log,out=lab
    pub=publish_investigation(audit,log,src,out)
    folder=out/'generations'/pub['generation']
    report=json.loads((folder/'report.json').read_bytes())
    report['review_candidates'][1]['module']='pkg.fabricated'
    report['record_sha256']=sha(canonical({k:v for k,v in report.items() if k!='record_sha256'}))
    (folder/'report.json').write_bytes(canonical(report))
    seal={'schema':'ae09/seal/v1','generation':pub['generation'],
          'artifacts':{'report.json':sha(canonical(report))}}
    (folder/'SEAL.json').write_bytes(canonical(seal))
    (out/'LATEST.json').write_bytes(canonical({'status':'completed','generation':pub['generation'],'seal_sha256':sha(canonical(seal))}))
    with pytest.raises(ValueError):verify_publication(out,audit,log,src)


def test_changed_source_refuses_replay(lab):
    src,audit,log,out=lab
    publish_investigation(audit,log,src,out)
    (src/'pkg'/'boom.py').write_text('def explode():\n    pass\n')
    with pytest.raises(ValueError):verify_publication(out,audit,log,src)


def test_modified_log_refuses_replay(lab):
    src,audit,log,out=lab
    publish_investigation(audit,log,src,out)
    log.write_text(log.read_text().replace('ValueError','RuntimeError'))
    with pytest.raises(ValueError):verify_publication(out,audit,log,src)


def test_no_frames_is_not_clean(lab):
    src,audit,log,_=lab
    log.write_text('Validation failed (exit=1)\n')
    report=build_report(audit,log,src)
    assert report['assurance_status']=='inconclusive'
    assert 'no_parseable_source_frame' in report['issues']
    assert not report['review_candidates']


def test_bad_path_is_not_scoped(lab):
    src,audit,log,_=lab
    log.write_text('  File "../../pkg/boom.py", line 2, in explode\n')
    result=build_report(audit,log,src)
    assert result['assurance_status']=='inconclusive'
    assert result['observations'][0]['match_strategy']=='unsafe'
    assert not result['review_candidates']


def test_ambiguous_paths_are_not_assumed(lab):
    src,audit,log,_=lab
    assert _match_path('/ci/boom.py',{'a/boom.py': 'a','b/boom.py':'b'})[0]=='ambiguous'
    assert _match_path('../pkg/boom.py',{'pkg/boom.py': 'a'})[0]=='unsafe'


def test_budget_does_not_hide_review_scope(lab):
    src,audit,log,_=lab
    r=build_report(audit,log,src,max_candidates=1)
    assert r['assurance_status']=='inconclusive'
    assert 'graph_traversal_budget_exceeded' in r['issues']
    r=build_report(audit,log,src,max_depth=0)
    assert r['assurance_status']=='inconclusive'
    assert 'graph_traversal_budget_exceeded' in r['issues']


def test_policy_graph_integrity_from_original(lab):
    src,audit,log,_=lab
    from audit_engine.semantic_audit.ae01.publication import verify
    assert verify(audit,source_root=src)['findings']==1
    assert len(build_report(audit,log,src)['review_candidates'])==3


def test_source_audit_incomplete_propagates(lab):
    src,audit,log,_=lab
    (src/'pkg'/'new.py').write_text('x=1\n')
    with pytest.raises(ValueError):build_report(audit,log,src)


def test_symlink_log_rejected(lab,tmp_path):
    src,audit,log,_=lab
    link=tmp_path/'link.log';link.symlink_to(log)
    with pytest.raises(ValueError):build_report(audit,link,src)


def test_symlink_output_rejected(lab,tmp_path):
    src,audit,log,out=lab
    proxy=tmp_path/'redirect';proxy.symlink_to(tmp_path)
    with pytest.raises(ValueError):publish_investigation(audit,log,src,proxy/'report')


def test_output_boundary_rejected(lab):
    src,audit,log,_=lab
    with pytest.raises(ValueError):publish_investigation(audit,log,src,src/'audit-output')
    with pytest.raises(ValueError):publish_investigation(audit,log,src,audit/'child')


def test_bad_log_bytes_rejected(lab):
    src,audit,log,_=lab
    log.write_bytes(b'\xffabc')
    with pytest.raises(UnicodeDecodeError):build_report(audit,log,src)
    log.write_bytes(b'a\x00b')
    with pytest.raises(ValueError):build_report(audit,log,src)
    log.write_bytes(b'x'*2_000_001)
    with pytest.raises(ValueError):build_report(audit,log,src)


def test_no_raw_log_secrets_in_published_json(lab):
    src,audit,log,out=lab
    log.write_text(log.read_text()+'PASSWORD=TOPSECRET_NOT_FOR_REPORT\n')
    published=publish_investigation(audit,log,src,out)
    body=(out/'generations'/published['generation']/'report.json').read_bytes()
    assert b'TOPSECRET_NOT_FOR_REPORT' not in body
    assert b'/runner/src/' not in body
    assert 'log_sha256' in json.loads(body)


def test_bounded_pytest_and_gh_annotation(lab):
    src,audit,log,_=lab
    log.write_text('::error file=pkg/boom.py,line=2::bad\n'
                   'pkg/boom.py:2: ValueError: crash\n'
                   'pkg/boom.py:2:in explode\n')
    r=build_report(audit,log,src)
    assert len(r['observations'])==3
    assert r['assurance_status']=='bounded_correlation'
    assert {o['kind'] for o in r['observations']}=={'github_annotation','pytest_summary','pytest_frame'}


def test_determinism(lab):
    src,audit,log,_=lab
    a=build_report(audit,log,src)
    b=build_report(audit,log,src)
    assert a==b
    assert verify_report(a,audit,log,src)['verified']


def test_failed_publication_invalidates_latest(lab):
    src,audit,log,out=lab
    publish_investigation(audit,log,src,out)
    log.write_bytes(b'\x00bad')
    with pytest.raises(ValueError):publish_investigation(audit,log,src,out)
    assert json.loads((out/'LATEST.json').read_bytes())['status']=='failed'
    with pytest.raises(ValueError):verify_publication(out,audit,log,src)


def test_cli_replay(lab):
    src,audit,log,out=lab
    cmd=[sys.executable,'-m','audit_engine.semantic_audit.ae09','--ae01-output',str(audit),
         '--log-file',str(log),'--source-root',str(src),'--output',str(out)]
    proc=subprocess.run(cmd,capture_output=True,text=True,timeout=12)
    assert proc.returncode==0,proc.stderr
    again=subprocess.run(cmd+['--verify'],capture_output=True,text=True,timeout=12)
    assert again.returncode==0,again.stderr


def test_incomplete_when_unique_basename_only(lab):
    src,audit,log,_=lab
    log.write_text('  File "/ci/boom.py", line 2, in explode\n')
    r=build_report(audit,log,src)
    assert r['assurance_status']=='inconclusive'
    assert 'weak_basename_path_match' in r['issues']
    assert r['review_candidates']


def test_static_edge_is_not_runtime_causality(lab):
    src,audit,log,_=lab
    assert build_report(audit,log,src)['conclusion']=='review_hypotheses_only_not_proven_root_cause'


def test_actual_python_subprocess_traceback(lab):
    """Independently generate a genuine traceback, not a log fixture shaped by AE-09."""
    src,audit,log,_=lab
    call=subprocess.run([sys.executable,'-c','from pkg.service import run; run()'],
        env={**os.environ,'PYTHONPATH':str(src),'PYTHONDONTWRITEBYTECODE':'1'},text=True,capture_output=True,timeout=8)
    assert call.returncode!=0
    assert 'ValueError:' in call.stderr
    log.write_text(call.stderr)
    report=build_report(audit,log,src)
    assert any(row.get('source_path')=='pkg/boom.py' for row in report['observations'])
    assert any(row['module']=='pkg.caller' for row in report['review_candidates'])
    assert any(sig['exception_class']=='ValueError' for sig in report['failure_signals'])
    # Source-less top-level <string> frames are explicitly unresolved; no false-clean claim.
    assert report['assurance_status']=='inconclusive'


def test_exception_messages_not_stored(lab):
    src,audit,log,_=lab
    log.write_text(log.read_text().replace('controlled fixture','PRIVATE_SESSION_TOKEN_SHOULD_NOT_LEAK'))
    report=build_report(audit,log,src)
    assert b'PRIVATE_SESSION_TOKEN_SHOULD_NOT_LEAK' not in json.dumps(report).encode()
    assert any(sig['exception_class']=='ValueError' for sig in report['failure_signals'])


def test_no_static_defect_inferred_from_runtime_traceback(lab):
    src,audit,log,_=lab
    r=build_report(audit,log,src)
    assert 'confirmed_root_cause' not in r
    assert not any('runtime_verified_defect' in str(value) for value in r.values())


def test_multiple_occurrences_not_collapsed(lab):
    src,audit,log,_=lab
    log.write_text(log.read_text()*2)
    r=build_report(audit,log,src)
    assert len(r['observations'])==2
    assert r['observations'][0]['observation_id']!=r['observations'][1]['observation_id']


def test_no_extracted_exceptions_in_clean_log(lab):
    src,audit,log,_=lab
    log.write_text('targeted: passed (exit=0)\nregression: passed (exit=0)\n')
    r=build_report(audit,log,src)
    assert not r['failure_signals']
    assert r['assurance_status']=='inconclusive'


def test_absolute_path_with_parent_traversal_is_unsafe(lab):
    src,audit,log,_=lab
    log.write_text('  File "/ci/../../pkg/boom.py", line 2, in explode\n')
    report=build_report(audit,log,src)
    assert report['observations'][0]['match_strategy']=='unsafe'
    assert report['assurance_status']=='inconclusive'
    assert not report['review_candidates']


def test_timestamped_github_actions_traceback_and_error(lab):
    src,audit,log,_=lab
    log.write_text(
        '2026-10-15T10:25:49.0102500Z Traceback (most recent call last):\n'
        '2026-10-15T10:25:49.0102510Z   File "/runner/src/pkg/boom.py", line 2, in explode\n'
        '2026-10-15T10:25:49.0102520Z ##[error]ValueError: runtime failure\n'
    )
    r=build_report(audit,log,src)
    assert r['observations'][0]['source_path']=='pkg/boom.py'
    assert r['failure_signals'][0]['exception_class']=='ValueError'
    assert r['assurance_status']=='bounded_correlation'


def test_exception_signal_limit_fails_closed(lab):
    src,audit,log,_=lab
    log.write_text(log.read_text()+('RuntimeError: runtime failed\n'*513))
    r=build_report(audit,log,src)
    assert len(r['failure_signals'])==512
    assert 'signal_limit_exceeded' in r['issues']
    assert r['assurance_status']=='inconclusive'
