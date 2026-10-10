"""G3.4.12: tamper-evident, per-run validation-evidence catalogs.

This CLI is housed on main and consumes artifacts from the selected branch.
It does NOT establish cryptographic signing or a persistent GitHub-wide index.
Historical lookup operates on downloaded/extracted workflow artifact folders.
"""
from __future__ import annotations

import argparse
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import re
import stat
import sys
from zipfile import ZipFile, BadZipFile, ZIP_STORED

ENTRY_SCHEMA = 'validation-evidence-catalog-entry/v1'
INDEX_SCHEMA = 'validation-evidence-catalog-index/v1'
RECEIPT_SCHEMA = 'validation-evidence-cas-receipt/v1'
BUNDLE_SCHEMA = 'validation-evidence-cas/v1'
SHA256 = re.compile(r'[0-9a-f]{64}\Z')
COMMIT = re.compile(r'[0-9a-f]{40,64}\Z')
SAFE_MEMBER = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z')
MAX_BUNDLE = 65 * 1024 * 1024
MAX_MEMBERS = 25
MAX_UNCOMPRESSED = 64 * 1024 * 1024


class CatalogError(ValueError):
    """The artifact, index, or binding violates its documented contract."""


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(obj: object) -> bytes:
    return (json.dumps(obj, sort_keys=True, separators=(',', ':'),
                       ensure_ascii=False, allow_nan=False) + '\n').encode('utf-8')


def safe_regular(path: Path, limit: int) -> bytes:
    """Read a single, non-symlink regular file with a strict size cap."""
    if path.is_symlink():
        raise CatalogError(f'Symlink forbidden: {path}')
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    except OSError as exc:
        raise CatalogError(f'Cannot open artifact: {path}') from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise CatalogError(f'Unsafe or oversized artifact: {path}')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            raw = stream.read(limit + 1)
        if len(raw) > limit:
            raise CatalogError(f'Artifact exceeds size cap: {path}')
        return raw
    finally:
        os.close(fd)


def json_obj(blob: bytes, what: str) -> dict:
    try:
        val = json.loads(blob)
    except (ValueError, UnicodeDecodeError) as exc:
        raise CatalogError(f'Invalid {what} JSON') from exc
    if not isinstance(val, dict):
        raise CatalogError(f'{what} must be a JSON object')
    return val


def detached(directory: Path, name: str, size: int) -> bytes:
    blob = safe_regular(directory / name, size)
    actual = safe_regular(directory / f'{name.removesuffix(".json")}.sha256', 512)
    wanted = f'{sha(blob)}  {name}\n'.encode('ascii')
    if actual != wanted:
        raise CatalogError(f'Detached digest mismatch for {name}')
    return blob


def digest_field(data: dict, field: str) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not SHA256.fullmatch(value):
        raise CatalogError(f'Invalid {field}')
    return value


def committed_field(data: dict, field: str) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not COMMIT.fullmatch(value):
        raise CatalogError(f'Invalid {field}')
    return value


def verify_zip(blob: bytes, *, expected_report_sha: str, expected_report: bytes) -> None:
    """Independently check ZIP member hashes, manifest and exact report binding."""
    if len(blob) > MAX_BUNDLE:
        raise CatalogError('Bundle exceeds size cap')
    try:
        with ZipFile(BytesIO(blob)) as archive:
            infos = archive.infolist()
            if not 3 <= len(infos) <= MAX_MEMBERS:
                raise CatalogError('Unexpected bundle member count')
            names = [i.filename for i in infos]
            if len(set(names)) != len(names):
                raise CatalogError('Duplicate ZIP member')
            size = 0
            members = {}
            for item in infos:
                if (not SAFE_MEMBER.fullmatch(item.filename) or item.is_dir()
                        or item.compress_type != ZIP_STORED
                        or item.file_size > MAX_BUNDLE):
                    raise CatalogError('Unsafe ZIP member')
                if item.create_system == 3 and stat.S_IFMT(item.external_attr >> 16) not in (0, stat.S_IFREG):
                    raise CatalogError('Nonregular ZIP member')
                size += item.file_size
                if size > MAX_UNCOMPRESSED:
                    raise CatalogError('Uncompressed evidence exceeds size cap')
                members[item.filename] = archive.read(item)
    except (BadZipFile, OSError, EOFError, RuntimeError) as exc:
        raise CatalogError('Invalid ZIP archive') from exc
    manifest_raw = members.pop('bundle_manifest.json', None)
    if manifest_raw is None:
        raise CatalogError('Missing bundle manifest')
    manifest = json_obj(manifest_raw, 'bundle manifest')
    if manifest.get('schema_version') != BUNDLE_SCHEMA or canonical(manifest) != manifest_raw:
        raise CatalogError('Invalid bundle manifest schema or canonicalization')
    expected = [{'name': n, 'sha256': sha(b), 'size_bytes': len(b)} for n, b in sorted(members.items())]
    if manifest.get('files') != expected or manifest.get('report_sha256') != expected_report_sha:
        raise CatalogError('Bundle manifest digest mismatch')
    if members.get('validation_report.json') != expected_report:
        raise CatalogError('Bundle contains different validation report')
    if members.get('validation_report.sha256') != f'{expected_report_sha}  validation_report.json\n'.encode('ascii'):
        raise CatalogError('Bundle contains invalid detached report digest')


def evidence_binding(evidence: Path) -> dict:
    if not evidence.is_dir() or evidence.is_symlink():
        raise CatalogError('Evidence root must be a real directory')
    report_blob = detached(evidence, 'validation_report.json', 4 * 1024 * 1024)
    report = json_obj(report_blob, 'validation report')
    receipt_blob = detached(evidence, 'bundle_receipt.json', 16 * 1024)
    receipt = json_obj(receipt_blob, 'bundle receipt')
    if receipt.get('schema_version') != RECEIPT_SCHEMA:
        raise CatalogError('Unsupported receipt schema')
    digest = digest_field(receipt, 'bundle_sha256')
    report_digest = digest_field(receipt, 'report_sha256')
    if report_digest != sha(report_blob):
        raise CatalogError('Receipt does not bind report bytes')
    for receipt_key, report_key in (
        ('source_profile_id', 'profile_id'),
        ('source_commit_sha', 'target_commit_sha'),
        ('engine_commit_sha', 'engine_commit_sha'),
        ('github_run_id', 'github_run_id'),
        ('github_run_attempt', 'github_run_attempt'),
    ):
        if receipt.get(receipt_key) != report.get(report_key):
            raise CatalogError(f'Receipt/report disagreement: {receipt_key}')
    commit = committed_field(report, 'target_commit_sha')
    engine = committed_field(report, 'engine_commit_sha')
    profile = report.get('profile_id')
    branch = report.get('target_branch')
    if not isinstance(profile, str) or not re.fullmatch(r'G\d+(?:\.\d+)+', profile):
        raise CatalogError('Invalid profile ID')
    if not isinstance(branch, str) or not branch or len(branch) > 255:
        raise CatalogError('Invalid branch')
    if report.get('status') != 'passed':
        raise CatalogError('Catalog publication requires passed verification')
    count = report.get('results', {}).get('targeted', {}).get('counts', {})
    if not isinstance(count, dict) or type(count.get('tests')) is not int or count['tests'] <= 0:
        raise CatalogError('No targeted tests in successful evidence')
    if report['results']['targeted'].get('status') != 'passed':
        raise CatalogError('Targeted tests did not pass')
    for identity in ('github_run_id', 'github_run_attempt'):
        value = report.get(identity)
        if not isinstance(value, str) or not re.fullmatch(r'[0-9]{1,20}', value):
            raise CatalogError(f'Invalid {identity}')
    bytes_size = receipt.get('byte_size')
    if type(bytes_size) is not int or bytes_size <= 0 or bytes_size > MAX_BUNDLE:
        raise CatalogError('Invalid receipt bundle length')
    if (evidence / 'bundles').is_symlink() or not (evidence / 'bundles').is_dir():
        raise CatalogError('Unsafe bundle directory')
    blob = safe_regular(evidence / 'bundles' / f'{digest}.validation.zip', MAX_BUNDLE)
    if sha(blob) != digest or len(blob) != bytes_size:
        raise CatalogError('Bundle checksum or length mismatch')
    verify_zip(blob, expected_report_sha=report_digest, expected_report=report_blob)
    return {
        'schema_version': ENTRY_SCHEMA,
        'bundle_sha256': digest,
        'bundle_size_bytes': bytes_size,
        'report_sha256': report_digest,
        'receipt_sha256': sha(receipt_blob),
        'profile_id': profile,
        'branch': branch,
        'source_commit_sha': commit,
        'engine_commit_sha': engine,
        'github_run_id': str(report.get('github_run_id') or ''),
        'github_run_attempt': str(report.get('github_run_attempt') or ''),
        'status': 'passed',
        'targeted_tests': count['tests'],
        'regression_status': report.get('results', {}).get('regression', {}).get('status'),
    }


def catalog_paths(evidence: Path):
    folder = evidence / 'catalog'
    return folder, folder / 'catalog_entry.json', folder / 'index.json'


def create_catalog(evidence: Path) -> dict:
    record = evidence_binding(evidence)
    folder, entry_file, index_file = catalog_paths(evidence)
    if folder.exists() or folder.is_symlink():
        raise CatalogError('Catalog already exists; refusing to overwrite')
    folder.mkdir()
    try:
        entry_bytes = canonical(record)
        index = {'schema_version': INDEX_SCHEMA, 'entries': [record]}
        index_bytes = canonical(index)
        for name, data in (
            ('catalog_entry.json', entry_bytes),
            ('catalog_entry.sha256', f'{sha(entry_bytes)}  catalog_entry.json\n'.encode()),
            ('index.json', index_bytes),
            ('index.sha256', f'{sha(index_bytes)}  index.json\n'.encode()),
        ):
            target = folder / name
            with target.open('xb') as output:
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
        return record
    except BaseException:
        # A failed publication is never silently claimed to be a valid catalog.
        raise


def verify_catalog(evidence: Path) -> dict:
    expected = evidence_binding(evidence)
    folder, _, _ = catalog_paths(evidence)
    if not folder.is_dir() or folder.is_symlink():
        raise CatalogError('Missing or unsafe catalog directory')
    if {x.name for x in folder.iterdir()} != {
        'catalog_entry.json', 'catalog_entry.sha256', 'index.json', 'index.sha256'
    }:
        raise CatalogError('Unexpected catalog members')
    entry = json_obj(detached(folder, 'catalog_entry.json', 16 * 1024), 'catalog entry')
    index_raw = detached(folder, 'index.json', 32 * 1024)
    index = json_obj(index_raw, 'catalog index')
    if entry != expected or index != {'schema_version': INDEX_SCHEMA, 'entries': [expected]}:
        raise CatalogError('Catalog record disagrees with verified bundle')
    if canonical(entry) != safe_regular(folder / 'catalog_entry.json', 16 * 1024):
        raise CatalogError('Noncanonical catalog record')
    if canonical(index) != index_raw:
        raise CatalogError('Noncanonical catalog index')
    return entry


def locate(roots: list[Path], *, profile: str | None, commit: str | None, run_id: str | None) -> list[dict]:
    matches = []
    for evidence in roots:
        record = verify_catalog(evidence)
        if profile and record['profile_id'] != profile:
            continue
        if commit and record['source_commit_sha'] != commit:
            continue
        if run_id and record['github_run_id'] != run_id:
            continue
        matches.append({'evidence_directory': str(evidence), **record})
    return sorted(matches, key=lambda x: (x['source_commit_sha'], x['github_run_id'], x['bundle_sha256']))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    commands = p.add_subparsers(dest='command', required=True)
    for cmd in ('build', 'verify'):
        sp = commands.add_parser(cmd)
        sp.add_argument('--evidence-dir', required=True, type=Path)
    search = commands.add_parser('find')
    search.add_argument('--evidence-dir', type=Path, action='append', required=True,
                        help='Repeat for each downloaded and extracted GitHub Actions artifact directory')
    search.add_argument('--profile')
    search.add_argument('--commit')
    search.add_argument('--run-id')
    search.add_argument('--require-match', action='store_true')
    args = p.parse_args(argv)
    try:
        if args.command == 'build':
            record = create_catalog(args.evidence_dir)
            print('Catalog built: ' + record['bundle_sha256'])
        elif args.command == 'verify':
            record = verify_catalog(args.evidence_dir)
            print('Catalog verified: ' + record['bundle_sha256'])
        else:
            matches = locate(args.evidence_dir, profile=args.profile,
                             commit=args.commit, run_id=args.run_id)
            if args.require_match and not matches:
                raise CatalogError('No verified historical records matched requested filters')
            print(json.dumps(matches, indent=2, sort_keys=True))
        return 0
    except (CatalogError, OSError, ValueError, KeyError, TypeError) as exc:
        print('Catalog verification failed: ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
