"""Independent adversarial tests for the central G3.4.12 catalog engine."""
from __future__ import annotations

import copy
import hashlib
import json
from io import BytesIO
from pathlib import Path
import sys
import tempfile
import unittest
from zipfile import ZipFile, ZipInfo, ZIP_STORED

sys.path.insert(0, str(Path(__file__).resolve().parent.parent if Path(__file__).parent.name == 'tests' else Path(__file__).resolve().parent))
import validation_catalog as c


def create_sample(root: Path):
    evidence = root / 'evidence'
    evidence.mkdir()
    report = {
        'schema_version': '1.1', 'status': 'passed',
        'profile_id': 'G3.4.12', 'target_branch': 'stage1/section-uuids',
        'target_commit_sha': 'a' * 40, 'engine_commit_sha': 'b' * 40,
        'github_run_id': '12345', 'github_run_attempt': '1',
        'results': {
            'targeted': {'status': 'passed', 'exit_code': 0,
                         'counts': {'tests': 3, 'failures': 0, 'errors': 0, 'skipped': 0}},
            'regression': {'status': 'passed', 'exit_code': 0,
                           'counts': {'tests': 3, 'failures': 0, 'errors': 0, 'skipped': 0}},
        },
    }
    rbytes = c.canonical(report)
    (evidence / 'validation_report.json').write_bytes(rbytes)
    (evidence / 'validation_report.sha256').write_text(c.sha(rbytes) + '  validation_report.json\n')
    members = {
        'validation_report.json': rbytes,
        'validation_report.sha256': (evidence / 'validation_report.sha256').read_bytes(),
    }
    manifest = {'schema_version': c.BUNDLE_SCHEMA, 'report_sha256': c.sha(rbytes),
                'files': [{'name': n, 'sha256': c.sha(b), 'size_bytes': len(b)}
                          for n, b in sorted(members.items())]}
    members['bundle_manifest.json'] = c.canonical(manifest)
    output = BytesIO()
    with ZipFile(output, 'w', compression=ZIP_STORED) as z:
        for name, blob in sorted(members.items()):
            info = ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_STORED
            info.create_system = 3
            info.external_attr = 0o100600 << 16
            z.writestr(info, blob)
    bundle = output.getvalue()
    (evidence / 'bundles').mkdir()
    (evidence / 'bundles' / f'{c.sha(bundle)}.validation.zip').write_bytes(bundle)
    receipt = {
        'schema_version': c.RECEIPT_SCHEMA, 'bundle_sha256': c.sha(bundle),
        'byte_size': len(bundle), 'report_sha256': c.sha(rbytes),
        'source_profile_id': report['profile_id'],
        'source_commit_sha': report['target_commit_sha'],
        'engine_commit_sha': report['engine_commit_sha'],
        'github_run_id': report['github_run_id'],
        'github_run_attempt': report['github_run_attempt'],
    }
    blob = c.canonical(receipt)
    (evidence / 'bundle_receipt.json').write_bytes(blob)
    (evidence / 'bundle_receipt.sha256').write_text(c.sha(blob) + '  bundle_receipt.json\n')
    return evidence


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.evidence = create_sample(Path(self.tmp.name))

    def test_build_and_verify(self):
        item = c.create_catalog(self.evidence)
        self.assertEqual(item, c.verify_catalog(self.evidence))
        self.assertEqual(item['profile_id'], 'G3.4.12')

    def test_no_overwrite(self):
        c.create_catalog(self.evidence)
        with self.assertRaises(c.CatalogError):
            c.create_catalog(self.evidence)

    def test_cli_roundtrip(self):
        self.assertEqual(c.main(['build', '--evidence-dir', str(self.evidence)]), 0)
        self.assertEqual(c.main(['verify', '--evidence-dir', str(self.evidence)]), 0)
        self.assertEqual(c.main(['find', '--evidence-dir', str(self.evidence), '--profile', 'G3.4.12']), 0)

    def test_lookup_filters(self):
        c.create_catalog(self.evidence)
        self.assertEqual(len(c.locate([self.evidence], profile='G3.4.12', commit=None, run_id=None)), 1)
        self.assertEqual(c.locate([self.evidence], profile='G3.4.11', commit=None, run_id=None), [])
        self.assertEqual(len(c.locate([self.evidence], profile=None, commit='a' * 40, run_id='12345')), 1)

    def test_require_match_fails_closed(self):
        c.create_catalog(self.evidence)
        self.assertEqual(c.main(['find', '--evidence-dir', str(self.evidence),
                                '--profile', 'G3.4.11', '--require-match']), 1)

    def test_wrong_receipt_sha(self):
        (self.evidence / 'bundle_receipt.sha256').write_text('0' * 64 + '  bundle_receipt.json\n')
        with self.assertRaises(c.CatalogError): c.create_catalog(self.evidence)

    def test_wrong_bundle_bytes(self):
        p = next((self.evidence / 'bundles').glob('*'))
        p.write_bytes(p.read_bytes() + b'tamper')
        with self.assertRaises(c.CatalogError): c.create_catalog(self.evidence)

    def test_wrong_bundle_manifest(self):
        p = next((self.evidence / 'bundles').glob('*'))
        raw = p.read_bytes().replace(b'validation-evidence-cas/v1', b'validation-evidence-cas/v2')
        p.write_bytes(raw)
        with self.assertRaises(c.CatalogError): c.create_catalog(self.evidence)

    def test_report_status_failed(self):
        p = self.evidence / 'validation_report.json'
        report = json.loads(p.read_bytes())
        report['status'] = 'failed'
        raw = c.canonical(report)
        p.write_bytes(raw)
        (self.evidence / 'validation_report.sha256').write_text(c.sha(raw) + '  validation_report.json\n')
        with self.assertRaises(c.CatalogError): c.create_catalog(self.evidence)

    def test_forged_profile_even_with_rehashed_receipt(self):
        receipt = json.loads((self.evidence / 'bundle_receipt.json').read_text())
        receipt['source_profile_id'] = 'G3.4.11'
        blob = c.canonical(receipt)
        (self.evidence / 'bundle_receipt.json').write_bytes(blob)
        (self.evidence / 'bundle_receipt.sha256').write_text(c.sha(blob) + '  bundle_receipt.json\n')
        with self.assertRaises(c.CatalogError): c.create_catalog(self.evidence)

    def test_wrong_run_id(self):
        receipt = json.loads((self.evidence / 'bundle_receipt.json').read_text())
        receipt['github_run_id'] = '555'
        raw = c.canonical(receipt)
        (self.evidence / 'bundle_receipt.json').write_bytes(raw)
        (self.evidence / 'bundle_receipt.sha256').write_text(c.sha(raw) + '  bundle_receipt.json\n')
        with self.assertRaises(c.CatalogError): c.create_catalog(self.evidence)

    def test_catalog_entry_tamper_rejected(self):
        c.create_catalog(self.evidence)
        p = self.evidence / 'catalog' / 'catalog_entry.json'
        p.write_bytes(p.read_bytes() + b' ')
        with self.assertRaises(c.CatalogError): c.verify_catalog(self.evidence)

    def test_catalog_forgery_with_matching_digest_rejected(self):
        c.create_catalog(self.evidence)
        p = self.evidence / 'catalog' / 'catalog_entry.json'
        entry = json.loads(p.read_text())
        entry['profile_id'] = 'G3.4.13'
        blob = c.canonical(entry)
        p.write_bytes(blob)
        (self.evidence / 'catalog' / 'catalog_entry.sha256').write_text(c.sha(blob) + '  catalog_entry.json\n')
        with self.assertRaises(c.CatalogError): c.verify_catalog(self.evidence)

    def test_catalog_index_tamper_rejected(self):
        c.create_catalog(self.evidence)
        p = self.evidence / 'catalog' / 'index.json'
        obj = json.loads(p.read_bytes())
        obj['entries'] = []
        blob = c.canonical(obj)
        p.write_bytes(blob)
        (self.evidence / 'catalog' / 'index.sha256').write_text(c.sha(blob) + '  index.json\n')
        with self.assertRaises(c.CatalogError): c.verify_catalog(self.evidence)

    @unittest.skipUnless(hasattr(Path, 'symlink_to'), 'Symlink support required')
    def test_symlink_bundle_rejected(self):
        original = next((self.evidence / 'bundles').glob('*'))
        dest = original.with_suffix('.backup')
        original.rename(dest)
        original.symlink_to(dest)
        with self.assertRaises(c.CatalogError): c.create_catalog(self.evidence)

    def test_unexpected_catalog_file_rejected(self):
        c.create_catalog(self.evidence)
        (self.evidence / 'catalog' / 'surprise').write_text('x')
        with self.assertRaises(c.CatalogError): c.verify_catalog(self.evidence)

    def test_existing_historical_artifacts_verify_by_digest(self):
        # A per-run artifact is self-describing and remains searchable when copied elsewhere.
        c.create_catalog(self.evidence)
        other = Path(self.tmp.name) / 'moved'
        self.evidence.rename(other)
        self.assertEqual(len(c.locate([other], profile=None, commit=None, run_id='12345')), 1)

    def test_bundle_directory_symlink_rejected(self):
        bundles = self.evidence / 'bundles'
        outside = Path(self.tmp.name) / 'outside'
        bundles.rename(outside)
        bundles.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(c.CatalogError): c.create_catalog(self.evidence)

    def test_missing_run_id_rejected(self):
        report_file = self.evidence / 'validation_report.json'
        report = json.loads(report_file.read_bytes())
        report['github_run_id'] = None
        raw = c.canonical(report)
        report_file.write_bytes(raw)
        (self.evidence / 'validation_report.sha256').write_text(c.sha(raw) + '  validation_report.json\n')
        with self.assertRaises(c.CatalogError): c.create_catalog(self.evidence)


if __name__ == '__main__': unittest.main()
