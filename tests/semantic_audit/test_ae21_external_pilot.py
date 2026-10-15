"""G9.23: external-benchmark pilot and independently defined behavior controls.

These tests are intentionally GitHub-only and require exact code-pinned fixtures.
They do not assume AE-15 detects algorithmic faults it cannot model.
"""
import copy
import json
import shutil
from pathlib import Path

import pytest

from audit_engine.semantic_audit.ae21.evaluate import (
    PINNED, admit_pilot, evaluate_pilot, replay_equivalent,
)
from audit_engine.semantic_audit.ae01.publication import canonical

FIXTURES=Path(__file__).parent/'fixtures'/'ae21_pilot'


def test_exact_reference_admission_and_external_provenance_limits():
    reference=admit_pilot(FIXTURES)
    assert len(reference['cases'])==3 and len(PINNED)==8
    assert reference['cases'][0]['category']=='external_curated_semantic_transcription'
    assert all(x['category']=='locally_authored_synthetic_control' for x in reference['cases'][1:])
    assert (FIXTURES/'QUIXBUGS_LICENSE.txt').is_file()


def test_no_implicit_trusted_execution():
    with pytest.raises(PermissionError,match='explicit trusted opt-in'):
        evaluate_pilot(FIXTURES)


def test_behavioral_gold_separate_from_detection_and_no_false_authority():
    result=evaluate_pilot(FIXTURES,explicit_trusted_execution=True)
    assert result['schema']=='ae21/curated_external_pilot_evaluation/v1'
    assert result['oracle_reproduced_pairs']==result['pilot_case_count']==3
    assert result['pilot_gate']=='reference_oracles_reproduced'
    assert result['external_source_pairs']==1 and result['synthetic_pairs']==2
    assert result['verified_findings']==result['verified_root_causes']==[]
    assert 'not upstream byte-authenticated' in result['source_authority']
    assert result['cases'][0]['defective_static_signal']['status']=='out_of_scope'
    assert result['cases'][0]['correct_static_signal']['status']=='out_of_scope'
    matrix=result['supported_scope_confusion']
    assert sum(matrix[k] for k in ('tp','fp','fn','tn','unknown'))==4
    assert matrix['out_of_scope_pairs']==1
    assert replay_equivalent(FIXTURES,result,explicit_trusted_execution=True)


def test_tampered_report_with_matching_recomputed_digest_still_rejected():
    result=evaluate_pilot(FIXTURES,explicit_trusted_execution=True)
    tampered=copy.deepcopy(result);tampered['cases'][0]['oracle_reproduced']=False
    assert not replay_equivalent(FIXTURES,tampered,explicit_trusted_execution=True)


def test_changed_fixture_even_with_updated_reference_is_rejected(tmp_path):
    copy_root=tmp_path/'casebook';shutil.copytree(FIXTURES,copy_root)
    src=copy_root/'branch_unbound_faulty.py'
    src.write_bytes(src.read_bytes()+b'\n# hidden edit\n')
    with pytest.raises(ValueError,match='source or membership'):
        admit_pilot(copy_root)


def test_reference_rehash_does_not_change_code_pinned_truth(tmp_path):
    root=tmp_path/'casebook';shutil.copytree(FIXTURES,root)
    ref=root/'REFERENCE.json';obj=json.loads(ref.read_bytes());obj['cases'][0]['expected']['defective']={'kind':'return','value':7}
    ref.write_bytes(canonical(obj))
    with pytest.raises(ValueError,match='source or membership'):
        admit_pilot(root)


def test_extra_member_and_removed_license_rejected(tmp_path):
    root=tmp_path/'casebook';shutil.copytree(FIXTURES,root)
    (root/'extra.py').write_text('raise RuntimeError("should not execute")\n')
    with pytest.raises(ValueError,match='membership'):
        admit_pilot(root)
    (root/'extra.py').unlink();(root/'QUIXBUGS_LICENSE.txt').unlink()
    with pytest.raises(ValueError,match='membership'):
        admit_pilot(root)


def test_symlink_source_rejected_before_execution(tmp_path):
    root=tmp_path/'casebook';shutil.copytree(FIXTURES,root)
    original=root/'quixbugs_gcd_faulty.py';original.unlink()
    try:original.symlink_to(FIXTURES/'quixbugs_gcd_faulty.py')
    except (OSError,NotImplementedError):pytest.skip('Symlink unavailable')
    with pytest.raises(ValueError): admit_pilot(root)


def test_invalid_raw_reference_serialization_rejected_even_when_valid_json(tmp_path):
    root=tmp_path/'casebook';shutil.copytree(FIXTURES,root)
    ref=root/'REFERENCE.json'
    # The admission layer rejects byte change even when parsed meaning agrees.
    ref.write_bytes(json.dumps(json.loads(ref.read_bytes()),indent=2).encode())
    with pytest.raises(ValueError):admit_pilot(root)
