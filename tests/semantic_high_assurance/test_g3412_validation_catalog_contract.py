"""G3.4.12 branch contract and proof-bundle integration checks."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

from audit_engine.semantic_audit.high_assurance.validation_evidence_store import (
    EvidenceBundleError, EvidenceBundleStore, inspect_bundle,
)


REPO = Path(__file__).resolve().parents[2]
PROFILE = REPO / 'validation' / 'profiles' / 'G3.4.12.yaml'


def test_profile_targets_real_tests_and_requires_regression():
    data = yaml.safe_load(PROFILE.read_text(encoding='utf-8'))
    assert data['id'] == 'G3.4.12'
    assert data['regression'] == {'enabled': True, 'path': 'tests/'}
    assert data['target_tests'] == ['tests/semantic_high_assurance/test_g3412_validation_catalog_contract.py']
    assert all((REPO / path).is_file() for path in data['target_tests'])


def test_prior_content_addressed_publisher_exists():
    script = REPO / 'tools' / 'publish_validation_evidence_bundle.py'
    assert script.is_file(), 'G3.4.10 publisher must not be removed'
    text = script.read_text(encoding='utf-8')
    assert 'EvidenceBundleStore' in text
    assert 'bundle_receipt.json' in text


def valid_evidence(tmp_path):
    folder = tmp_path / 'evidence'
    folder.mkdir()
    junit = b'<testsuite tests="1" failures="0" errors="0" skipped="0"><testcase name="ok"/></testsuite>'
    names = {'targeted.xml': junit, 'targeted.log': b'1 passed', 'engine-unit-tests.log': b'1 passed'}
    for name, blob in names.items():
        (folder / name).write_bytes(blob)
    def rec(name):
        return {'path': name, 'sha256': hashlib.sha256(names[name]).hexdigest(), 'size_bytes': len(names[name])}
    report = {
        'schema_version': '1.1', 'status': 'passed', 'profile_id': 'G3.4.12',
        'target_commit_sha': 'a' * 40, 'engine_commit_sha': 'b' * 40,
        'engine_unit_tests': {'status': 'passed', 'count': 1, 'log': rec('engine-unit-tests.log')},
        'results': {'targeted': {
            'status': 'passed', 'exit_code': 0,
            'counts': {'tests': 1, 'failures': 0, 'errors': 0, 'skipped': 0},
            'junit': rec('targeted.xml'), 'log': rec('targeted.log')
        }}
    }
    payload = (json.dumps(report, sort_keys=True, separators=(',', ':')) + '\n').encode()
    (folder / 'validation_report.json').write_bytes(payload)
    (folder / 'validation_report.sha256').write_text(
        hashlib.sha256(payload).hexdigest() + '  validation_report.json\n', encoding='ascii'
    )
    return folder


def test_bundle_receipt_is_deterministic_and_independently_openable(tmp_path):
    evidence = valid_evidence(tmp_path)
    store = EvidenceBundleStore(tmp_path / 'store')
    receipt = store.publish(evidence)
    result = store.verify(receipt.bundle_sha256)
    assert (result.bundle_sha256, result.report_sha256) == (receipt.bundle_sha256, receipt.report_sha256)
    raw = (store.root / f'{receipt.bundle_sha256}.validation.zip').read_bytes()
    assert inspect_bundle(raw) == (receipt.bundle_sha256, receipt.report_sha256)
    assert store.publish(evidence).committed is False


def test_bundle_modified_after_publication_rejected(tmp_path):
    evidence = valid_evidence(tmp_path)
    store = EvidenceBundleStore(tmp_path / 'store')
    receipt = store.publish(evidence)
    blob = store.root / f'{receipt.bundle_sha256}.validation.zip'
    blob.write_bytes(blob.read_bytes() + b'modified')
    with pytest.raises(EvidenceBundleError):
        store.verify(receipt.bundle_sha256)


def test_bundle_member_path_traversal_rejected():
    from io import BytesIO
    from zipfile import ZipFile
    stream = BytesIO()
    with ZipFile(stream, 'w') as archive:
        archive.writestr('../hidden.txt', b'x')
    with pytest.raises(EvidenceBundleError):
        inspect_bundle(stream.getvalue())


def test_catalog_schema_enforces_bundle_and_run_identity():
    schema = json.loads((REPO / 'validation/catalog/schema.json').read_text(encoding='utf-8'))
    Draft202012Validator.check_schema(schema)
    record = {
        'schema_version': 'validation-evidence-catalog-entry/v1',
        'bundle_sha256': '1' * 64, 'bundle_size_bytes': 2024,
        'report_sha256': '2' * 64, 'receipt_sha256': '3' * 64,
        'profile_id': 'G3.4.12', 'branch': 'stage1/section-uuids',
        'source_commit_sha': '4' * 40, 'engine_commit_sha': '5' * 40,
        'github_run_id': '123', 'github_run_attempt': '1',
        'status': 'passed', 'targeted_tests': 6, 'regression_status': 'passed',
    }
    validator = Draft202012Validator(schema)
    assert not list(validator.iter_errors(record))
    record['bundle_sha256'] = 'fake'
    assert list(validator.iter_errors(record))
