"""Independent AE-10 release gate. Verifies physical ZIP members + G9.11 target paths."""
from __future__ import annotations
import hashlib
from pathlib import Path, PurePosixPath
import re
import stat
import zipfile
import yaml

PROFILE='STAGE1_SECTION_UUIDS/validation/profiles/G9.11.yaml'
REQUIRED={
 'README.md','PATCH_MAP.md','LOCAL_VALIDATION_RESULTS.md','SHA256SUMS.txt',
 PROFILE,
 *('STAGE1_SECTION_UUIDS/audit_engine/semantic_audit/ae10/'+n for n in
   ('__init__.py','__main__.py','science.py','publication.py','METHOD_AND_LIMITATIONS.md')),
 *('STAGE1_SECTION_UUIDS/tests/semantic_audit/'+n for n in
   ('test_ae10_science.py','test_ae10_release.py')),
 *('STAGE1_SECTION_UUIDS/tests/fixtures/ae10/'+n for n in ('experiment.json','spec.json','statement_elastic_modulus.txt','statement_displacement_limit.txt')),
 'STAGE1_SECTION_UUIDS/tools/check_ae10_patch.py',
}


def check(zip_path:Path|str,repository_root:Path|str|None=None)->dict:
    path=Path(zip_path)
    root=Path(repository_root) if repository_root else None
    with zipfile.ZipFile(path) as z:
        files={}
        for info in z.infolist():
            name=info.filename
            if info.is_dir():
                continue
            parts=PurePosixPath(name).parts
            if (name.startswith('/') or '\\' in name or '\x00' in name or not parts or
                any(p in ('','..','.') for p in name.split('/')) or ':' in parts[0] or
                any(p=='__pycache__' for p in parts) or name.endswith(('.pyc','.pyo'))):
                raise ValueError('Unsafe release member: '+name)
            mode=info.external_attr>>16
            if stat.S_IFMT(mode)==stat.S_IFLNK:
                raise ValueError('Symlink ZIP member prohibited')
            if name in files:
                raise ValueError('Duplicate ZIP file')
            if info.file_size > 2_000_000:
                raise ValueError('Oversized release member')
            files[name]=z.read(name)
        if not REQUIRED.issubset(files):
            raise ValueError('Missing AE-10 release files: '+str(sorted(REQUIRED-set(files))))
        lines=files['SHA256SUMS.txt'].decode('utf-8').splitlines()
        digests={}
        for line in lines:
            m=re.fullmatch(r'([0-9a-f]{64})  (.+)',line)
            if not m or m.group(2) in digests:
                raise ValueError('Malformed SHA256SUMS')
            digests[m.group(2)]=m.group(1)
        if set(digests)!=set(files)-{'SHA256SUMS.txt'}:
            raise ValueError('Checksum coverage incomplete')
        for name,digest in digests.items():
            if hashlib.sha256(files[name]).hexdigest()!=digest:
                raise ValueError('Checksum mismatch: '+name)
        profile=yaml.safe_load(files[PROFILE])
        if not isinstance(profile,dict) or profile.get('id')!='G9.11':
            raise ValueError('Missing G9.11 identity')
        selected=profile.get('target_tests')
        if not isinstance(selected,list) or not selected:
            raise ValueError('Missing G9.11 target tests')
        for target in selected:
            if not isinstance(target,str) or not target.startswith('tests/') or '..' in PurePosixPath(target).parts:
                raise ValueError('Unsafe declared test target')
            packaged='STAGE1_SECTION_UUIDS/'+target
            if packaged not in files and (root is None or not (root/target).is_file()):
                raise ValueError('Missing declared target '+target)
        if profile.get('regression')!={'enabled':True,'path':'tests/'}:
            raise ValueError('Profile regression contract changed')
        for fixture in ('experiment.json','spec.json','statement_elastic_modulus.txt','statement_displacement_limit.txt'):
            if not files['STAGE1_SECTION_UUIDS/tests/fixtures/ae10/'+fixture]:
                raise ValueError('Missing fixture bytes')
        # Check fixture source digests rather than trusting the ZIP checksum alone.
        import json
        base='STAGE1_SECTION_UUIDS/tests/fixtures/ae10/'
        gold=json.loads(files[base+'spec.json'])
        for item in gold['artifacts']:
            if hashlib.sha256(files[base+item['path']]).hexdigest()!=item['sha256']:
                raise ValueError('Evidence fixture hash mismatch')
        for item in gold['claims']:
            if hashlib.sha256(files[base+item['statement_path']]).hexdigest()!=item['statement_sha256']:
                raise ValueError('Claim statement fixture hash mismatch')
        return {'profile':'G9.11','files':len(files),'test_targets':len(selected)}


def main():
    import argparse,json
    p=argparse.ArgumentParser();p.add_argument('archive');p.add_argument('--repository-root')
    args=p.parse_args()
    print(json.dumps(check(args.archive,args.repository_root),sort_keys=True))

if __name__=='__main__':main()
