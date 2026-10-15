"""AE-14/G9.16 release ZIP integrity and strict member validation."""
from __future__ import annotations
import hashlib
import stat
import sys
import zipfile
from pathlib import Path

PROFILE = 'STAGE1_SECTION_UUIDS/validation/profiles/G9.16.yaml'
FILES = frozenset({
    'STAGE1_SECTION_UUIDS/audit_engine/semantic_audit/ae14/__init__.py',
    'STAGE1_SECTION_UUIDS/audit_engine/semantic_audit/ae14/lexical.py',
    'STAGE1_SECTION_UUIDS/audit_engine/semantic_audit/ae01/source.py',
    'STAGE1_SECTION_UUIDS/audit_engine/semantic_audit/ae01/pipeline.py',
    'STAGE1_SECTION_UUIDS/tests/semantic_audit/test_ae14_lexical_semantics.py',
    'STAGE1_SECTION_UUIDS/tests/semantic_audit/test_ae14_release.py',
    PROFILE,
    'STAGE1_SECTION_UUIDS/tools/check_ae14_patch.py',
    'README.md','PATCH_MAP.md','LOCAL_VALIDATION_RESULTS.md','SHA256SUMS.txt',
    'VALIDATION_LOGS/selected.log','VALIDATION_LOGS/fresh_install_selected.log',
    'VALIDATION_LOGS/full_regression.log','VALIDATION_LOGS/full_regression.exit',
    'VALIDATION_LOGS/isolated_solver_initial.log',
    'VALIDATION_LOGS/isolated_solver_baseline.log',
    'VALIDATION_LOGS/isolated_solver_retry.log',
})


def validate(path: Path) -> None:
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        if len(infos) != len(FILES):
            raise ValueError('Incorrect archive member count')
        found: set[str] = set()
        total = 0
        for entry in infos:
            name = entry.filename
            segments = name.split('/')
            if (name in found or name.startswith('/') or '\\' in name or ':' in name or
                name.endswith('/') or any(part in ('', '.', '..') for part in segments) or
                entry.is_dir()):
                raise ValueError(f'Unsafe path or duplicate entry: {name}')
            found.add(name)
            mode = stat.S_IFMT(entry.external_attr >> 16)
            if mode not in (0, stat.S_IFREG):
                raise ValueError(f'Nonregular member: {name}')
            if (entry.file_size > 8_000_000 or
                (entry.compress_size == 0 and entry.file_size > 0) or
                entry.file_size > 500 * max(1, entry.compress_size)):
                raise ValueError(f'Excessive member: {name}')
            total += entry.file_size
            if total > 16_000_000:
                raise ValueError('Excessive total uncompressed size')
        if found != FILES:
            raise ValueError(f'Member mismatch: missing {sorted(FILES - found)}; extra {sorted(found - FILES)}')
        expected = {}
        for line in archive.read('SHA256SUMS.txt').decode('ascii').splitlines():
            h, sep, name = line.partition('  ')
            if (not sep or len(h) != 64 or not all(c in '0123456789abcdef' for c in h)
                    or name not in found or name == 'SHA256SUMS.txt' or name in expected):
                raise ValueError('Malformed checksum line')
            expected[name] = h
        if set(expected) != found - {'SHA256SUMS.txt'}:
            raise ValueError('Incomplete checksum manifest')
        for name, h in expected.items():
            if hashlib.sha256(archive.read(name)).hexdigest() != h:
                raise ValueError(f'Checksum mismatch for {name}')
        profile = archive.read(PROFILE).decode('utf-8')
        if not ('id: G9.16' in profile and 'test_ae14_lexical_semantics.py' in profile and
                'test_ae131_protected_contracts.py' in profile and 'regression:' in profile):
            raise ValueError('Wrong validation profile or missing compatibility scope')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Usage: python tools/check_ae14_patch.py RELEASE.zip')
    validate(Path(sys.argv[1]))
    print('G9.16 archive integrity and membership validated')
