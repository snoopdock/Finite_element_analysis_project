"""G9.21 independent manual outcome labels and source replay of two uploaded G9.20 runs."""
from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

import pytest
from audit_engine.semantic_audit.ae01.publication import canonical,sha
from audit_engine.semantic_audit.ae19 import (
    admit,interpret_step_logs,evaluate_casebook,publish_casebook,verify_casebook
)

CORPUS=Path(__file__).resolve().parent/'fixtures'/'ae19_history'
FAILED='H01_g920_initial_failure'
PASSED='H02_g920_corrected_pass'


def _clone(tmp_path):
    new=tmp_path/'casebook'
    shutil.copytree(CORPUS,new)
    return new


def _rebind(root,relative):
    name=relative.as_posix()
    manifest_path=root/'MANIFEST.json'
    manifest=json.loads(manifest_path.read_bytes())
    manifest['sha256'][name]=sha((root/relative).read_bytes())
    manifest_path.write_bytes(canonical(manifest))


def test_two_real_uploaded_outcome_references_are_byte_pinned():
    manifest,labels=admit(CORPUS)
    assert manifest['cases']==[FAILED,PASSED]
    assert len(manifest['archive_sha256'])==2
    assert labels['cases'][FAILED]['final']=='failed'
    assert labels['cases'][PASSED]['final']=='passed'
    assert labels['cases'][FAILED]['published'] is True  # failure evidence publication != success


def test_parser_separates_failed_then_corrected_success():
    bad=interpret_step_logs(CORPUS,FAILED)
    good=interpret_step_logs(CORPUS,PASSED)
    assert bad['profile']==good['profile']=='G9.20'
    assert (bad['targeted'],bad['regression'],bad['final'],bad['detached'])==('failed',)*4
    assert (good['targeted'],good['regression'],good['final'],good['detached'])==('passed',)*4
    assert bad['bundle_sha256']!=good['bundle_sha256']
    assert bad['published'] and bad['catalog_verified']
    assert good['published'] and good['catalog_verified']


def test_historical_corpus_reuses_AE16_and_preserves_failed_run_incompleteness():
    report=evaluate_casebook(CORPUS)
    assert report['candidate_gate']=='pass_historical_run_outcome_concordance_only'
    assert report['case_count']==report['exact_manual_case_matches']==2
    assert report['ae16_assurance_preserved_count']==2
    assert report['false_clean_cases']==0
    assert report['verified_findings']==report['verified_root_causes']==[]
    cases={x['id']:x for x in report['cases']}
    assert cases[FAILED]['ae16_assurance']=='incomplete_or_inconsistent'
    assert cases[FAILED]['ae16_issue_count']>=1
    assert not cases[FAILED]['is_complete_successful_supplied_record']
    assert cases[PASSED]['ae16_assurance']=='consistent_declared_observations_unattested'
    assert cases[PASSED]['is_complete_successful_supplied_record']
    assert all(not case['external_run_authenticated'] for case in cases.values())


def test_source_replay_and_sealed_publication(tmp_path):
    out=tmp_path/'published'
    first=publish_casebook(CORPUS,out)
    assert first['candidate_gate']=='pass_historical_run_outcome_concordance_only'
    assert first==verify_casebook(CORPUS,out)
    assert first==publish_casebook(CORPUS,out)
    assert len(list((out/'generations').iterdir()))==1


def test_changed_log_bytes_are_rejected(tmp_path):
    corpus=_clone(tmp_path)
    p=corpus/'cases'/PASSED/'step7.txt'
    p.write_bytes(p.read_bytes().replace(b'targeted: passed',b'targeted: failed'))
    with pytest.raises(ValueError,match='changed'):
        admit(corpus)


def test_changed_independent_labels_are_rejected(tmp_path):
    corpus=_clone(tmp_path)
    p=corpus/'labels.json'
    obj=json.loads(p.read_bytes());obj['cases'][FAILED]['final']='passed'
    p.write_bytes(canonical(obj))
    with pytest.raises(ValueError,match='changed'):
        admit(corpus)


def test_valid_rebinding_does_not_force_false_concordance(tmp_path):
    corpus=_clone(tmp_path)
    relative=Path('cases')/PASSED/'step7.txt'
    p=corpus/relative
    p.write_bytes(p.read_bytes().replace(b'targeted: passed (exit=0)',b'targeted: failed (exit=1)'))
    _rebind(corpus,relative)
    assert evaluate_casebook(corpus)['candidate_gate']=='fail_historical_reference'


def test_missing_result_is_unknown_not_silently_pass(tmp_path):
    corpus=_clone(tmp_path)
    relative=Path('cases')/PASSED/'step7.txt'
    p=corpus/relative
    p.write_bytes(p.read_bytes().replace(b'targeted: passed (exit=0)',b'targeted: OMITTED (exit=0)'))
    _rebind(corpus,relative)
    obs=interpret_step_logs(corpus,PASSED)
    assert obs['targeted']=='unknown'
    scored=evaluate_casebook(corpus)
    assert scored['candidate_gate']=='fail_historical_reference'
    assert scored['ae16_assurance_preserved_count']==2


def test_conflicting_result_markers_are_rejected(tmp_path):
    corpus=_clone(tmp_path)
    relative=Path('cases')/PASSED/'step7.txt'
    p=corpus/relative
    p.write_bytes(p.read_bytes()+b'\ntargeted: failed (exit=1)\n')
    _rebind(corpus,relative)
    with pytest.raises(ValueError,match='Ambiguous'):
        interpret_step_logs(corpus,PASSED)


def test_wrong_detached_profile_rejected(tmp_path):
    corpus=_clone(tmp_path)
    relative=Path('cases')/PASSED/'step8.txt'
    p=corpus/relative
    p.write_bytes(p.read_bytes().replace(b'profile=G9.20',b'profile=G9.21'))
    _rebind(corpus,relative)
    with pytest.raises(ValueError,match='profile differs'):
        interpret_step_logs(corpus,PASSED)


def test_catalog_mismatch_rejected_even_when_bundle_was_published(tmp_path):
    corpus=_clone(tmp_path)
    relative=Path('cases')/PASSED/'step11.txt'
    p=corpus/relative
    p.write_bytes(p.read_bytes().replace(b'Catalog verified: 333ad281',b'Catalog verified: a33ad281'))
    _rebind(corpus,relative)
    with pytest.raises(ValueError,match='catalog and bundle'):
        interpret_step_logs(corpus,PASSED)


def test_missing_and_unlisted_files_rejected(tmp_path):
    corpus=_clone(tmp_path)
    (corpus/'cases'/FAILED/'step8.txt').unlink()
    with pytest.raises(ValueError):admit(corpus)


def test_tampered_sealed_report_rejected(tmp_path):
    out=tmp_path/'sealed'; receipt=publish_casebook(CORPUS,out)
    report=out/'generations'/receipt['generation']/'evaluation.json'
    doc=json.loads(report.read_bytes());doc['false_clean_cases']=999
    report.write_bytes(canonical(doc))
    with pytest.raises(ValueError):verify_casebook(CORPUS,out)


def test_output_cannot_overlap_source(tmp_path):
    with pytest.raises(ValueError):publish_casebook(CORPUS,CORPUS/'result')
