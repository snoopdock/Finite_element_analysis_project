"""GitHub-only regression oracles for three documented, real project defects.

The archived Python source execution occurs only from committed, hardcoded
SHA-256-pinned snapshots. This is trusted developer test code, NOT a sandbox and
NOT a mechanism for running uploaded or model-generated code.
"""
import json
import shutil
from pathlib import Path

import pytest

from audit_engine.semantic_audit.ae01.publication import canonical, sha
from audit_engine.semantic_audit.ae20.evaluate import (
    EXPECTED, SNAPSHOTS, _files, evaluate_trusted_historical_regressions,
)
from audit_engine.semantic_audit.ae19.evaluate import admit

TESTS = Path(__file__).resolve().parent
SNAP = TESTS/'fixtures'/'ae20_faults'/'snapshots'
AE18 = TESTS/'fixtures'/'ae18_reference'
AE19 = TESTS/'fixtures'/'ae19_history'


def test_reference_snapshots_match_released_actual_source_bytes():
    assert _files(SNAP) == SNAPSHOTS
    assert len(SNAPSHOTS) == 5
    assert (SNAP/'ae19_noncanonical_labels.json').read_bytes()[-1:] != b'\n'
    assert (SNAP/'ae19_after_labels.json').read_bytes().endswith(b'\n')
    assert json.loads((SNAP/'ae19_before_labels.json').read_bytes())['cases']['H01_g920_initial_failure']['catalog_verified'] is True
    assert json.loads((SNAP/'ae19_after_labels.json').read_bytes())['cases']['H01_g920_initial_failure']['catalog_verified'] is False


def test_no_implicit_execution_authority():
    with pytest.raises(PermissionError, match='explicit opt-in'):
        evaluate_trusted_historical_regressions(SNAP,AE18,AE19)


def test_three_historical_before_after_oracles_with_runtime_reproduction():
    result=evaluate_trusted_historical_regressions(SNAP,AE18,AE19,explicit_trusted_execution=True)
    assert result['schema']=='ae20/pinned_historical_defect_oracles/v1'
    assert result['case_count']==result['exact_matches']==3
    assert result['candidate_gate']=='pass_trusted_historical_regression_oracles_only'
    assert all(row['exact_oracle_match'] for row in result['cases'])
    assert {row['id'] for row in result['cases']}==set(EXPECTED)
    assert result['verified_findings']==result['verified_root_causes']==[]
    assert 'not_github_api_authenticated' in result['source_authority']
    assert result['trusted_code_execution'].startswith('explicit_manual_test_only')


def test_changed_historical_source_blocked_before_execution(tmp_path):
    copied=tmp_path/'sources';shutil.copytree(SNAP,copied)
    file=copied/'ae18_before.py';file.write_bytes(file.read_bytes()+b'\n# unsanctioned source edit\n')
    with pytest.raises(ValueError,match='bytes or membership'):
        evaluate_trusted_historical_regressions(copied,AE18,AE19,explicit_trusted_execution=True)


def test_missing_or_extra_snapshots_rejected(tmp_path):
    copied=tmp_path/'source';shutil.copytree(SNAP,copied)
    (copied/'extra.py').write_text('pass\n')
    with pytest.raises(ValueError,match='membership'):_files(copied)
    (copied/'extra.py').unlink()
    (copied/'ae18_after.py').unlink()
    with pytest.raises(ValueError,match='membership'):_files(copied)


def test_snapshots_symlink_and_directory_rejected(tmp_path):
    copied=tmp_path/'source';shutil.copytree(SNAP,copied)
    target=copied/'ae18_before.py';target.unlink()
    try: target.symlink_to(SNAP/'ae18_before.py')
    except (OSError,NotImplementedError): pytest.skip('Cannot construct symlink')
    with pytest.raises(ValueError):_files(copied)


def test_reference_archive_checksum_rebinding_does_not_create_ground_truth(tmp_path):
    corpus=tmp_path/'cases';shutil.copytree(AE19,corpus)
    labels=corpus/'labels.json';value=json.loads(labels.read_bytes());value['cases']['H01_g920_initial_failure']['catalog_verified']=True
    labels.write_bytes(canonical(value))
    manifest=corpus/'MANIFEST.json';doc=json.loads(manifest.read_bytes());doc['sha256']['labels.json']=sha(labels.read_bytes());manifest.write_bytes(canonical(doc))
    # The modified corpus is byte-consistent, but historically inaccurate.
    admit(corpus)
    from audit_engine.semantic_audit.ae19.evaluate import evaluate_casebook
    assert evaluate_casebook(corpus)['candidate_gate']=='fail_historical_reference'


def test_manipulated_expected_contract_cannot_appear_perfect(monkeypatch):
    import audit_engine.semantic_audit.ae20.evaluate as phase
    wrong={k:dict(v) for k,v in phase.EXPECTED.items()}
    wrong['E01_empty_evidence_checkout']['after']='unjustified_clean_claim'
    monkeypatch.setattr(phase,'EXPECTED',wrong)
    result=phase.evaluate_trusted_historical_regressions(SNAP,AE18,AE19,explicit_trusted_execution=True)
    assert result['exact_matches']==2
    assert result['candidate_gate']=='fail_trusted_historical_regressions'
    assert result['verified_findings']==[]


def test_original_casebooks_are_not_changed(tmp_path):
    # Casebooks are read, but the reproducible experiments happen in scratch copies.
    before=[(p.relative_to(AE19).as_posix(),sha(p.read_bytes())) for p in sorted(AE19.rglob('*')) if p.is_file()]
    result=evaluate_trusted_historical_regressions(SNAP,AE18,AE19,explicit_trusted_execution=True)
    after=[(p.relative_to(AE19).as_posix(),sha(p.read_bytes())) for p in sorted(AE19.rglob('*')) if p.is_file()]
    assert before==after and result['exact_matches']==3
