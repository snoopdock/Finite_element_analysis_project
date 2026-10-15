"""Static archive admission and exact checksum verification; no patch imports."""
from __future__ import annotations
import hashlib
import sys
import zipfile
from pathlib import PurePosixPath

FILES=frozenset(['STAGE1_SECTION_UUIDS/audit_engine/semantic_audit/ae18/DESIGN_AND_LIMITATIONS.md',
 'STAGE1_SECTION_UUIDS/audit_engine/semantic_audit/ae18/__init__.py',
 'STAGE1_SECTION_UUIDS/audit_engine/semantic_audit/ae18/evaluate.py',
 'STAGE1_SECTION_UUIDS/audit_engine/semantic_audit/ae18/publication.py',
 'STAGE1_SECTION_UUIDS/tests/semantic_audit/fixtures/ae18_reference/MANIFEST.json',
 'STAGE1_SECTION_UUIDS/tests/semantic_audit/fixtures/ae18_reference/cases/R01_clean_required_check/declaration.json',
 'STAGE1_SECTION_UUIDS/tests/semantic_audit/fixtures/ae18_reference/cases/R01_clean_required_check/evidence/step.log',
 'STAGE1_SECTION_UUIDS/tests/semantic_audit/fixtures/ae18_reference/cases/R02_expected_negative_test/declaration.json',
 'STAGE1_SECTION_UUIDS/tests/semantic_audit/fixtures/ae18_reference/cases/R02_expected_negative_test/evidence/step.log',
 'STAGE1_SECTION_UUIDS/tests/semantic_audit/fixtures/ae18_reference/cases/R03_skipped_mandatory_check/declaration.json',
 'STAGE1_SECTION_UUIDS/tests/semantic_audit/fixtures/ae18_reference/cases/R03_skipped_mandatory_check/evidence/step.log',
 'STAGE1_SECTION_UUIDS/tests/semantic_audit/fixtures/ae18_reference/cases/R04_no_check_contract/declaration.json',
 'STAGE1_SECTION_UUIDS/tests/semantic_audit/fixtures/ae18_reference/cases/R04_no_check_contract/evidence/step.log',
 'STAGE1_SECTION_UUIDS/tests/semantic_audit/fixtures/ae18_reference/cases/R05_missing_log/declaration.json',
 'STAGE1_SECTION_UUIDS/tests/semantic_audit/fixtures/ae18_reference/cases/R06_claimed_success_nonzero_exit/declaration.json',
 'STAGE1_SECTION_UUIDS/tests/semantic_audit/fixtures/ae18_reference/cases/R06_claimed_success_nonzero_exit/evidence/step.log',
 'STAGE1_SECTION_UUIDS/tests/semantic_audit/fixtures/ae18_reference/cases/R07_unexpected_nested_failure/declaration.json',
 'STAGE1_SECTION_UUIDS/tests/semantic_audit/fixtures/ae18_reference/cases/R07_unexpected_nested_failure/evidence/step.log',
 'STAGE1_SECTION_UUIDS/tests/semantic_audit/fixtures/ae18_reference/cases/R08_missing_producer_artifact/declaration.json',
 'STAGE1_SECTION_UUIDS/tests/semantic_audit/fixtures/ae18_reference/cases/R08_missing_producer_artifact/evidence/step.log',
 'STAGE1_SECTION_UUIDS/tests/semantic_audit/fixtures/ae18_reference/cases/R09_correct_artifact_handoff/declaration.json',
 'STAGE1_SECTION_UUIDS/tests/semantic_audit/fixtures/ae18_reference/cases/R09_correct_artifact_handoff/evidence/consume.log',
 'STAGE1_SECTION_UUIDS/tests/semantic_audit/fixtures/ae18_reference/cases/R09_correct_artifact_handoff/evidence/consumer.bin',
 'STAGE1_SECTION_UUIDS/tests/semantic_audit/fixtures/ae18_reference/cases/R09_correct_artifact_handoff/evidence/producer.bin',
 'STAGE1_SECTION_UUIDS/tests/semantic_audit/fixtures/ae18_reference/cases/R09_correct_artifact_handoff/evidence/step.log',
 'STAGE1_SECTION_UUIDS/tests/semantic_audit/fixtures/ae18_reference/cases/R10_artifact_mismatch/declaration.json',
 'STAGE1_SECTION_UUIDS/tests/semantic_audit/fixtures/ae18_reference/cases/R10_artifact_mismatch/evidence/consume.log',
 'STAGE1_SECTION_UUIDS/tests/semantic_audit/fixtures/ae18_reference/cases/R10_artifact_mismatch/evidence/consumer.bin',
 'STAGE1_SECTION_UUIDS/tests/semantic_audit/fixtures/ae18_reference/cases/R10_artifact_mismatch/evidence/producer.bin',
 'STAGE1_SECTION_UUIDS/tests/semantic_audit/fixtures/ae18_reference/cases/R10_artifact_mismatch/evidence/step.log',
 'STAGE1_SECTION_UUIDS/tests/semantic_audit/fixtures/ae18_reference/cases/R11_undeclared_job_dependency/declaration.json',
 'STAGE1_SECTION_UUIDS/tests/semantic_audit/fixtures/ae18_reference/cases/R11_undeclared_job_dependency/evidence/consume.log',
 'STAGE1_SECTION_UUIDS/tests/semantic_audit/fixtures/ae18_reference/cases/R11_undeclared_job_dependency/evidence/consumer.bin',
 'STAGE1_SECTION_UUIDS/tests/semantic_audit/fixtures/ae18_reference/cases/R11_undeclared_job_dependency/evidence/producer.bin',
 'STAGE1_SECTION_UUIDS/tests/semantic_audit/fixtures/ae18_reference/cases/R11_undeclared_job_dependency/evidence/step.log',
 'STAGE1_SECTION_UUIDS/tests/semantic_audit/fixtures/ae18_reference/cases/R12_failed_job_claimed_run_success/declaration.json',
 'STAGE1_SECTION_UUIDS/tests/semantic_audit/fixtures/ae18_reference/cases/R12_failed_job_claimed_run_success/evidence/step.log',
 'STAGE1_SECTION_UUIDS/tests/semantic_audit/fixtures/ae18_reference/labels.json',
 'STAGE1_SECTION_UUIDS/tests/semantic_audit/test_ae18_effectiveness.py',
 'STAGE1_SECTION_UUIDS/tools/run_ae18_effectiveness.py',
 'STAGE1_SECTION_UUIDS/validation/profiles/G9.20.yaml',
 'STAGE1_SECTION_UUIDS/tools/check_ae18_patch.py',
 'STAGE1_SECTION_UUIDS/tests/semantic_audit/test_ae18_release.py'])
TOP=frozenset({'README.md','PATCH_MAP.md','VALIDATION_PLAN.md','SHA256SUMS.txt'})


def verify(path):
    with zipfile.ZipFile(path) as bundle:
        entries=bundle.infolist()
        if len(entries)>96:raise ValueError('Too many archive members')
        data={};total=0
        for entry in entries:
            name=entry.filename
            if (not name or name.startswith('/') or '\\' in name or ':' in name or
                any(x in ('','.','..') for x in name.split('/')) or
                entry.is_dir() or name in data):
                raise ValueError('Unsafe or duplicate archive entry')
            mode=(entry.external_attr>>16) & 0o170000
            if mode not in (0,0o100000):raise ValueError('Nonregular ZIP file entry')
            if entry.file_size>1_500_000:raise ValueError('ZIP member exceeds budget')
            total+=entry.file_size
            if total>6_000_000:raise ValueError('Total ZIP size exceeded')
            data[name]=bundle.read(entry)
        if set(data)!=FILES|TOP:raise ValueError('Patch ZIP membership differs from release manifest')
        seen=set()
        for line in data['SHA256SUMS.txt'].decode('ascii').splitlines():
            try:digest,name=line.split('  ',1)
            except ValueError as exc:raise ValueError('Bad checksum row') from exc
            if name=='SHA256SUMS.txt' or name in seen or name not in data:
                raise ValueError('Duplicate, missing or extraneous checksum entry')
            if hashlib.sha256(data[name]).hexdigest()!=digest:
                raise ValueError('Release checksum mismatch')
            seen.add(name)
        if seen!=set(data)-{'SHA256SUMS.txt'}:raise ValueError('Missing checksums')
        return {'members':len(data),'checksum_files':len(seen),
                'status':'static_integrity_verified_not_tests_executed'}

if __name__=='__main__':
    if len(sys.argv)!=2:raise SystemExit('usage: python check_ae18_patch.py PATCH.zip')
    print(verify(sys.argv[1]))
