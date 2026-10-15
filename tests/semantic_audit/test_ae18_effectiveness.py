"""AE-18 reference oracles are independent fixed labels, not analyzer outputs."""
import copy
import json
import shutil
from pathlib import Path

import pytest

from audit_engine.semantic_audit.ae01.publication import canonical,sha
from audit_engine.semantic_audit.ae18 import classify,evaluate_corpus,publish_evaluation,verify_evaluation
from audit_engine.semantic_audit.ae18.evaluate import _admit

CORPUS = Path(__file__).resolve().parent / 'fixtures' / 'ae18_reference'


def test_manually_labeled_reference_is_pinned_and_has_two_clean_controls():
    manifest, labels=_admit(CORPUS)
    assert len(manifest['cases'])==12
    assert len([v for v in labels['cases'].values() if not v['expected_issues']])==3
    assert labels['oracle_authority']=='manually_authored_controls_not_externally_adjudicated'
    assert len({x['kind'] for v in labels['cases'].values() for x in v['expected_issues']})>=9


def test_complete_bounded_reference_evaluation_is_exact():
    result=evaluate_corpus(CORPUS)
    assert result['candidate_gate']=='pass_controlled_reference_only'
    assert result['metrics']['case_count']==12
    assert result['metrics']['exact_case_matches']==12
    assert result['metrics']['false_positive']==0
    assert result['metrics']['false_negative']==0
    assert result['metrics']['false_clean_cases']==0
    assert result['metrics']['false_alarm_cases']==0
    assert result['metrics']['clean_controls']==3
    assert result['metrics']['correct_clean_controls']==3
    assert all(c['investigation_covers_all_observed_issues'] and
               c['assurance_matches_independent_expected_status'] for c in result['cases'])
    assert result['verified_findings']==[] and result['verified_root_causes']==[]
    assert result['source_authority']=='supplied_fixture_bytes_not_authenticated_runtime'


def test_published_reference_replays_without_claiming_real_causes(tmp_path):
    output=tmp_path/'out'
    first=publish_evaluation(CORPUS,output)
    assert first['candidate_gate']=='pass_controlled_reference_only'
    assert first==verify_evaluation(CORPUS,output)
    assert first==publish_evaluation(CORPUS,output)
    assert len(list((output/'generations').iterdir()))==1
    assert first['assurance']=='source_replayed_controlled_reference_not_external_effectiveness_proof'


def test_forged_reference_label_is_rejected(tmp_path):
    root=tmp_path/'reference'
    shutil.copytree(CORPUS,root)
    path=root/'labels.json'
    altered=json.loads(path.read_bytes());altered['cases']['R10_artifact_mismatch']['expected_issues']=[]
    path.write_bytes(canonical(altered))
    with pytest.raises(ValueError,match='changed'):
        _admit(root)


def test_changed_fixture_bytes_rejected(tmp_path):
    root=tmp_path/'reference'
    shutil.copytree(CORPUS,root)
    path=root/'cases'/'R10_artifact_mismatch'/'evidence'/'consumer.bin'
    path.write_bytes(b'unexpected bytes')
    with pytest.raises(ValueError):_admit(root)


def test_extra_reference_file_refused(tmp_path):
    root=tmp_path/'reference'
    shutil.copytree(CORPUS,root)
    (root/'cases'/'R01_clean_required_check'/'evidence'/'intruder.log').write_text('extra')
    with pytest.raises(ValueError,match='unlisted'):_admit(root)


def test_symlink_reference_rejected(tmp_path):
    root=tmp_path/'reference';shutil.copytree(CORPUS,root)
    (root/'escape').symlink_to(root/'labels.json')
    with pytest.raises(ValueError):_admit(root)


def test_comparison_detects_false_clean_and_false_alarm():
    item={'kind':'problem','subject':'test:one'}
    assert classify([item],[])['false_clean']
    assert classify([],[item])['false_alarm']
    assert classify([item],[])['false_negative']==1
    assert classify([],[item])['false_positive']==1
    assert classify([item],[item])['exact_match']
    with pytest.raises(ValueError):classify([item,item],[item])


def test_reject_tampered_published_evaluation(tmp_path):
    output=tmp_path/'out';receipt=publish_evaluation(CORPUS,output)
    doc=output/'generations'/receipt['generation']/'evaluation.json'
    content=json.loads(doc.read_bytes());content['metrics']['false_negative']=999
    doc.write_bytes(canonical(content))
    with pytest.raises(ValueError):verify_evaluation(CORPUS,output)


def test_forged_seal_does_not_bypass_identity_or_replay(tmp_path):
    output=tmp_path/'out';receipt=publish_evaluation(CORPUS,output)
    folder=output/'generations'/receipt['generation']
    content=json.loads((folder/'evaluation.json').read_bytes())
    content['metrics']['exact_case_matches']=0
    blob=canonical(content)
    (folder/'evaluation.json').write_bytes(blob)
    seal=canonical({'schema':'ae18/effectiveness_seal/v1','artifacts':{'evaluation.json':sha(blob)}})
    (folder/'SEAL.json').write_bytes(seal)
    (output/'LATEST.json').write_bytes(canonical({'status':'completed','generation':receipt['generation'],
                                                'seal_sha256':sha(seal)}))
    with pytest.raises(ValueError):verify_evaluation(CORPUS,output)


def test_output_cannot_overlap_reference_sources(tmp_path):
    with pytest.raises(ValueError):publish_evaluation(CORPUS,CORPUS/'result')
