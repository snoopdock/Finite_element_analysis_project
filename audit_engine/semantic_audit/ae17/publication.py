"""AE-17 sealed hypotheses: independently replay AE-16 from actual evidence bytes."""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

from audit_engine.semantic_audit.ae01.publication import (
    _atomic_bytes, _fsync_dir, _no_symlink_components, attempt, canonical, sha,
)
from .investigate import build_investigation, SCHEMA

SEAL_SCHEMA = 'ae17/investigation_seal/v1'
MEMBERS = frozenset({'investigation.json','SEAL.json'})


def _validate_roots(declaration_file, evidence_root, ae16_output, output_root,
                    ae01_output, source_root):
    paths=[Path(os.path.abspath(v)) if v is not None else None for v in
           (declaration_file,evidence_root,ae16_output,output_root,ae01_output,source_root)]
    for path in paths:
        if path is not None:_no_symlink_components(path)
    output=paths[3]
    if any(path is not None and (output==path or output in path.parents or path in output.parents)
           for path in (paths[1],paths[2],paths[4],paths[5])):
        raise ValueError('AE-17 output must not overlap any evidence/source directory')
    if output==paths[0] or output in paths[0].parents:
        raise ValueError('AE-17 output cannot overwrite declaration')
    return paths


def publish_investigation(declaration_file,evidence_root,ae16_output,output_root,*,
                          ae01_output=None,source_root=None,max_cases=80,max_context=64):
    decl,evidence,upstream,output,ae01,source=_validate_roots(
        declaration_file,evidence_root,ae16_output,output_root,ae01_output,source_root)
    with attempt(output):
        kwargs=dict(max_cases=max_cases,max_context=max_context,ae01_output=ae01,source_root=source)
        report=build_investigation(decl,evidence,upstream,**kwargs)
        if report!=build_investigation(decl,evidence,upstream,**kwargs):
            raise ValueError('Investigation inputs changed during capture')
        blob=canonical(report)
        if len(blob)>4_000_000:raise ValueError('AE-17 report exceeds publication budget')
        seal=canonical({'schema':SEAL_SCHEMA,'artifacts':{'investigation.json':sha(blob)}})
        generation='ae17-'+sha(canonical({'schema':SEAL_SCHEMA,'report':report}))[:28]
        generations=output/'generations';generations.mkdir(exist_ok=True)
        _no_symlink_components(generations)
        stage=Path(tempfile.mkdtemp(prefix='.ae17-stage-',dir=generations))
        try:
            _atomic_bytes(stage/'investigation.json',blob)
            _atomic_bytes(stage/'SEAL.json',seal)
            final=generations/generation
            if final.exists() or final.is_symlink():
                _no_symlink_components(final)
                if not final.is_dir() or {p.name for p in final.iterdir()}!=MEMBERS:
                    raise ValueError('Existing AE-17 generation has invalid membership')
                for name,data in (('investigation.json',blob),('SEAL.json',seal)):
                    _no_symlink_components(final/name)
                    if (final/name).read_bytes()!=data:raise ValueError('Existing generation content differs')
            else:
                os.rename(stage,final);_fsync_dir(generations)
            _atomic_bytes(output/'LATEST.json',canonical({'status':'completed','generation':generation,
                                                         'seal_sha256':sha(seal)}))
        finally:
            if stage.exists():shutil.rmtree(stage)
    return verify_investigation(decl,evidence,upstream,output,ae01_output=ae01,source_root=source)


def verify_investigation(declaration_file,evidence_root,ae16_output,output_root,*,
                         ae01_output=None,source_root=None):
    decl,evidence,upstream,output,ae01,source=_validate_roots(
        declaration_file,evidence_root,ae16_output,output_root,ae01_output,source_root)
    _no_symlink_components(output/'LATEST.json')
    pointer=json.loads((output/'LATEST.json').read_bytes())
    if (not isinstance(pointer,dict) or pointer.get('status')!='completed' or
        set(pointer)!={'status','generation','seal_sha256'}):
        raise ValueError('AE-17 last attempt did not complete')
    generation=pointer.get('generation')
    if (not isinstance(generation,str) or len(generation)!=33 or
        not generation.startswith('ae17-') or any(x not in '0123456789abcdef' for x in generation[5:])):
        raise ValueError('Invalid AE-17 generation identity')
    folder=output/'generations'/generation
    _no_symlink_components(folder)
    if not folder.is_dir() or {p.name for p in folder.iterdir()}!=MEMBERS:
        raise ValueError('AE-17 generation artifact membership mismatch')
    for name in MEMBERS:_no_symlink_components(folder/name)
    if (folder/'SEAL.json').stat().st_size>16_000 or (folder/'investigation.json').stat().st_size>4_000_000:
        raise ValueError('AE-17 published artifacts exceed admission limits')
    seal_bytes=(folder/'SEAL.json').read_bytes()
    if sha(seal_bytes)!=pointer['seal_sha256']:raise ValueError('AE-17 seal digest mismatch')
    seal=json.loads(seal_bytes)
    if (set(seal)!={'schema','artifacts'} or seal['schema']!=SEAL_SCHEMA or
        set(seal['artifacts'])!={'investigation.json'}):
        raise ValueError('Unsupported AE-17 seal')
    blob=(folder/'investigation.json').read_bytes()
    if sha(blob)!=seal['artifacts']['investigation.json']:raise ValueError('AE-17 report tampering')
    report=json.loads(blob)
    if canonical(report)!=blob:raise ValueError('AE-17 report is not canonical')
    if generation!='ae17-'+sha(canonical({'schema':SEAL_SCHEMA,'report':report}))[:28]:
        raise ValueError('AE-17 generation contents disagree with identity')
    if report.get('schema')!=SCHEMA or report.get('verified_findings')!=[] or report.get('verified_root_causes')!=[]:
        raise ValueError('Unauthorized promotion to verified conclusion')
    limits=report['bounds']
    if report!=build_investigation(decl,evidence,upstream,max_cases=limits['max_cases'],
                                   max_context=limits['max_context'],ae01_output=ae01,source_root=source):
        raise ValueError('AE-17 report disagrees with independently replayed source')
    return {'generation':generation,'snapshot_id':report['snapshot_id'],
            'cases':report['selected_issues'],'truncated':report['truncated'],
            'assurance':'unverified_hypothesis_plan_only',
            'verification':'AE-16_replayed_then_AE-17_replayed_no_root_cause_proof'}
