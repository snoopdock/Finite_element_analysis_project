"""Independently stated behavioral oracles for the AE-08 evaluator."""
from __future__ import annotations
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from audit_engine.semantic_audit.ae08.benchmark import (
    read_gold, evaluate, verify_result, survey, score_generation, write_report,
)
from audit_engine.semantic_audit.ae02.snapshots import load_generation

REPO = Path(__file__).resolve().parents[2]
POLICY = REPO/'specs/rules/architecture/no_production_to_experimental_dependency.yaml'
GOLD = REPO/'tests/fixtures/ae08_gold'
PERMITTED = REPO/'tests/fixtures/ae08_permitted'


def fixture(tmp_path, template=GOLD):
    root=tmp_path/'source'
    shutil.copytree(template,root)
    return root,root/'gold.json'


def run_eval(tmp_path,template=GOLD):
    root,gold=fixture(tmp_path,template)
    output=tmp_path/'artifacts'
    report=evaluate(root,gold,POLICY,output)
    return root,gold,output,report


def test_gold_positive_negative_dynamic_and_duplicate_oracles(tmp_path):
    root,gold,output,report=run_eval(tmp_path)
    assert report['imports']['expected']==10
    assert report['imports']['observed']==10
    assert report['imports']['exact_matches']==10
    assert report['architecture_findings']['expected']==3
    assert report['architecture_findings']['exact_matches']==3
    assert report['all_gold_annotations_matched'] is True
    assert report['engine_assurance_status']=='inconclusive'
    assert {'type_checking_only_dependency','unresolved_import'} <= set(report['engine_issue_kinds'])
    assert report['interpretation']=='fixture_agreement_with_incomplete_assurance'
    assert verify_result(report,root,gold,POLICY,output)['verified']


def test_permitted_fixture_has_zero_positive_labels_and_real_rule_application(tmp_path):
    root,gold,output,r=run_eval(tmp_path,PERMITTED)
    assert r['all_gold_annotations_matched']
    assert r['imports']['expected']==1
    assert r['architecture_findings']['expected']==0
    assert r['architecture_findings']['precision'] is None
    assert r['engine_assurance_status']=='complete_within_declared_scope'
    assert r['interpretation']=='fixture_agreement_bounded'
    assert load_generation(output).report['verified_compliance'] is True


def test_an_incorrect_manual_import_target_is_detected_not_averaged_away(tmp_path):
    root,gold,output,report=run_eval(tmp_path)
    labels=read_gold(root,gold)
    labels['imports'][0]['target']='not_actually_imported'
    derived=score_generation(load_generation(output),labels)
    assert derived['imports']['missing']==1
    assert derived['imports']['unexpected']==1
    assert derived['all_gold_annotations_matched'] is False
    assert derived['interpretation']=='gold_disagreement'


def test_missed_violation_and_spurious_violation_are_both_visible(tmp_path):
    root,gold,output,_=run_eval(tmp_path)
    labels=read_gold(root,gold)
    labels['violations'].pop()
    labels['violations'].append({'file':'stable.py','line':1,'column':0,'target':'experimental'})
    comparison=score_generation(load_generation(output),labels)['architecture_findings']
    assert comparison['missing']==1 and comparison['unexpected']==1
    assert comparison['recall']==pytest.approx(2/3)
    assert comparison['precision']==pytest.approx(2/3)


def test_modified_source_with_original_gold_is_rejected(tmp_path):
    root,gold,output,report=run_eval(tmp_path)
    (root/'app.py').write_text('import stable\n')
    with pytest.raises(ValueError,match='source hash'):
        read_gold(root,gold)
    with pytest.raises(ValueError):
        verify_result(report,root,gold,POLICY,output)


def test_changed_gold_labels_invalidate_report_even_if_sealed_source_same(tmp_path):
    root,gold,output,report=run_eval(tmp_path)
    data=json.loads(gold.read_text())
    data['violations']=[]
    gold.write_text(json.dumps(data))
    with pytest.raises(ValueError,match='Evaluation report'):
        verify_result(report,root,gold,POLICY,output)


def test_changed_report_digest_is_detected(tmp_path):
    root,gold,output,report=run_eval(tmp_path)
    forged=copy.deepcopy(report)
    forged['imports']['exact_matches']=9999
    with pytest.raises(ValueError,match='checksum'):
        verify_result(forged,root,gold,POLICY,output)


def test_resealed_but_fabricated_metrics_are_detected(tmp_path):
    from audit_engine.semantic_audit.ae01.publication import sha,canonical
    root,gold,output,report=run_eval(tmp_path)
    forged=copy.deepcopy(report)
    forged['imports']['recall']=0.001
    forged['report_sha256']=sha(canonical({k:v for k,v in forged.items() if k!='report_sha256'}))
    with pytest.raises(ValueError,match='does not match'):
        verify_result(forged,root,gold,POLICY,output)


def test_tampered_generation_is_rejected(tmp_path):
    root,gold,output,report=run_eval(tmp_path)
    gen=output/'generations'/report['generation_id']/'source_facts.json'
    gen.write_bytes(gen.read_bytes()+b' ')
    with pytest.raises(ValueError):
        verify_result(report,root,gold,POLICY,output)


def test_missing_and_extra_sources_break_closed_corpus(tmp_path):
    root,gold=fixture(tmp_path)
    (root/'unlabeled.py').write_text('import experimental\n')
    with pytest.raises(ValueError,match='exactly all'):
        read_gold(root,gold)
    (root/'unlabeled.py').unlink()
    (root/'app.py').unlink()
    with pytest.raises(ValueError,match='source'):
        read_gold(root,gold)


def test_symlinked_gold_file_and_source_are_rejected(tmp_path):
    root,gold=fixture(tmp_path)
    external=tmp_path/'outside.py'
    external.write_text('pass\n')
    (root/'app.py').unlink()
    (root/'app.py').symlink_to(external)
    with pytest.raises(ValueError,match='Symlink'):
        read_gold(root,gold)


def test_unlabeled_survey_reports_no_precision_and_no_compliance(tmp_path):
    root,_=fixture(tmp_path)
    result=survey(root)
    assert result['source_files']==11
    assert result['import_status_counts']['internal']==6
    assert result['import_status_counts']['unresolved']==1
    assert result['precision'] is None and result['recall'] is None
    assert result['verified_compliance'] is False
    assert result['survey_status']=='descriptive_only'


def test_survey_rejects_unparsable_as_complete(tmp_path):
    root,_=fixture(tmp_path)
    (root/'broken.py').write_bytes(b'def bad(:\n')
    result=survey(root)
    assert result['survey_status']=='incomplete'
    assert result['file_status_counts']['error']==1
    assert result['precision'] is None


def test_repeated_runs_are_identical_and_independently_verifiable(tmp_path):
    root,gold,output,first=run_eval(tmp_path)
    second=evaluate(root,gold,POLICY,output)
    assert first==second
    file=tmp_path/'output.json'
    write_report(file,first)
    assert json.loads(file.read_bytes())==first
    assert verify_result(json.loads(file.read_bytes()),root,gold,POLICY,output)['verified']


def test_reject_output_symlink(tmp_path):
    root,gold,output,r=run_eval(tmp_path)
    outside=tmp_path/'outside.json'; outside.write_text('safe')
    link=tmp_path/'link.json';link.symlink_to(outside)
    with pytest.raises(ValueError,match='Symlink'):
        write_report(link,r)
    assert outside.read_text()=='safe'


def test_cli_benchmark_and_detached_replay(tmp_path):
    root,gold=fixture(tmp_path)
    output=tmp_path/'artifacts'; result=tmp_path/'score.json'
    base=[sys.executable,'-m','audit_engine.semantic_audit.ae08','evaluate',
        '--source-root',str(root),'--gold',str(gold),'--policy',str(POLICY),
        '--audit-output',str(output),'--report',str(result)]
    proc=subprocess.run(base,cwd=REPO,capture_output=True,text=True,timeout=30)
    assert proc.returncode==0,proc.stderr
    replay=base.copy();replay[3]='verify'
    proc=subprocess.run(replay,cwd=REPO,capture_output=True,text=True,timeout=30)
    assert proc.returncode==0,proc.stderr
    assert json.loads(proc.stdout)['verified'] is True


def test_cli_detects_broken_manual_labeling(tmp_path):
    root,gold=fixture(tmp_path)
    payload=json.loads(gold.read_text())
    payload['imports'][0]['target']='wrong'
    gold.write_text(json.dumps(payload))
    cmd=[sys.executable,'-m','audit_engine.semantic_audit.ae08','evaluate',
        '--source-root',str(root),'--gold',str(gold),'--policy',str(POLICY),
        '--audit-output',str(tmp_path/'audit')]
    proc=subprocess.run(cmd,cwd=REPO,capture_output=True,text=True,timeout=30)
    assert proc.returncode==2
    assert json.loads(proc.stdout)['all_gold_annotations_matched'] is False


def test_symlinked_directory_cannot_hide_unlabeled_source(tmp_path):
    root,gold=fixture(tmp_path)
    outside=tmp_path/'nested'
    outside.mkdir()
    (outside/'untracked.py').write_text('import experimental\n')
    (root/'linked').symlink_to(outside,target_is_directory=True)
    with pytest.raises(ValueError,match='Symlink'):
        read_gold(root,gold)


def test_duplicate_independent_annotations_are_rejected(tmp_path):
    root,gold=fixture(tmp_path)
    labels=json.loads(gold.read_text())
    labels['imports'].append(copy.deepcopy(labels['imports'][0]))
    gold.write_text(json.dumps(labels))
    with pytest.raises(ValueError,match='duplicate'):
        read_gold(root,gold)


def test_policy_bytes_tampering_invalidates_detached_score(tmp_path):
    root,gold,output,report=run_eval(tmp_path)
    policy=tmp_path/'policy.yaml'
    policy.write_bytes(POLICY.read_bytes()+b'\n# adjusted after evaluation\n')
    with pytest.raises(ValueError):
        verify_result(report,root,gold,policy,output)


def test_new_unlabeled_import_not_counted_as_accuracy_claim(tmp_path):
    root,_=fixture(tmp_path)
    (root/'plain.py').write_text('import experimental\n')
    s=survey(root)
    assert s['precision'] is None and s['recall'] is None
    assert s['verified_compliance'] is False
    assert s['import_status_counts']['internal']==7
