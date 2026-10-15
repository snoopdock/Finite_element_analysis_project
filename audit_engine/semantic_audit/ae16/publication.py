"""AE-16 evidence-only generation: source-byte replay, never a runtime attestation."""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

from audit_engine.semantic_audit.ae01.publication import (
    _atomic_bytes, _fsync_dir, _no_symlink_components, attempt, canonical, sha,
)
from .operations import build_report

SEAL_SCHEMA = 'ae16/observation_seal/v1'
FILES = frozenset({'report.json','graph.json','SEAL.json'})


def _roots(declaration:Path,evidence:Path,output:Path):
    declaration=Path(os.path.abspath(declaration))
    evidence=Path(os.path.abspath(evidence))
    output=Path(os.path.abspath(output))
    for p in (declaration,evidence,output):_no_symlink_components(p)
    if evidence==output or evidence in output.parents or output in evidence.parents:
        raise ValueError('Operational report output must not overlap supplied evidence root')
    if declaration==output or output in declaration.parents:
        raise ValueError('Operational report output must not overwrite declaration')
    return declaration,evidence,output


def publish_observation(declaration:Path|str,evidence_root:Path|str,output_root:Path|str,*,
                        ae01_output:Path|str|None=None,source_root:Path|str|None=None,
                        max_ae09_candidates:int=100)->dict:
    declaration,evidence_root,output_root=_roots(Path(declaration),Path(evidence_root),Path(output_root))
    with attempt(output_root):
        report,graph=build_report(declaration,evidence_root,ae01_output=ae01_output,
                                   source_root=source_root,max_ae09_candidates=max_ae09_candidates)
        replay,again=build_report(declaration,evidence_root,ae01_output=ae01_output,
                                   source_root=source_root,max_ae09_candidates=max_ae09_candidates)
        if report!=replay or graph!=again:raise ValueError('Operational evidence changed during analysis')
        artifacts={'report.json':canonical(report),'graph.json':canonical(graph)}
        run_id='ae16-'+sha(canonical({'schema':SEAL_SCHEMA,'report':report,'graph':graph}))[:28]
        generations=output_root/'generations'
        generations.mkdir(exist_ok=True)
        _no_symlink_components(generations)
        stage=Path(tempfile.mkdtemp(dir=generations,prefix='.ae16-stage-'))
        try:
            for name,blob in artifacts.items():_atomic_bytes(stage/name,blob)
            seal=canonical({'schema':SEAL_SCHEMA,'artifacts':{key:sha(value) for key,value in artifacts.items()}})
            _atomic_bytes(stage/'SEAL.json',seal)
            final=generations/run_id
            if final.exists() or final.is_symlink():
                _no_symlink_components(final)
                if not final.is_dir() or set(p.name for p in final.iterdir())!=FILES:
                    raise ValueError('Existing operational generation membership mismatch')
                for name,blob in {**artifacts,'SEAL.json':seal}.items():
                    _no_symlink_components(final/name)
                    if (final/name).read_bytes()!=blob:raise ValueError('Existing operational generation differs')
            else:
                os.rename(stage,final)
                _fsync_dir(generations)
            _atomic_bytes(output_root/'LATEST.json',canonical({'status':'completed',
                        'generation':run_id,'seal_sha256':sha(seal)}))
        finally:
            if stage.exists():shutil.rmtree(stage)
    return verify_observation(declaration,evidence_root,output_root,ae01_output=ae01_output,
                              source_root=source_root)


def verify_observation(declaration:Path|str,evidence_root:Path|str,output_root:Path|str,*,
                       ae01_output:Path|str|None=None,source_root:Path|str|None=None)->dict:
    declaration,evidence_root,output_root=_roots(Path(declaration),Path(evidence_root),Path(output_root))
    _no_symlink_components(output_root/'LATEST.json')
    pointer=json.loads((output_root/'LATEST.json').read_bytes())
    if pointer.get('status')!='completed':raise ValueError('Last operational attempt is not completed')
    run_id=pointer.get('generation')
    if not isinstance(run_id,str) or not run_id.startswith('ae16-') or len(run_id)!=33 or any(c not in '0123456789abcdef' for c in run_id[5:]):
        raise ValueError('Invalid AE-16 generation identity')
    folder=output_root/'generations'/run_id
    _no_symlink_components(folder)
    if not folder.is_dir() or set(p.name for p in folder.iterdir())!=FILES:
        raise ValueError('Operational generation membership mismatch')
    for name in FILES:_no_symlink_components(folder/name)
    seal_data=(folder/'SEAL.json').read_bytes()
    if sha(seal_data)!=pointer.get('seal_sha256'):raise ValueError('Operational seal mismatch')
    seal=json.loads(seal_data)
    if seal.get('schema')!=SEAL_SCHEMA or set(seal.get('artifacts',{}))!=FILES-{'SEAL.json'}:
        raise ValueError('Invalid operational seal schema')
    docs={}
    for name,digest in seal['artifacts'].items():
        blob=(folder/name).read_bytes()
        if sha(blob)!=digest:raise ValueError('Operational artifact digest mismatch')
        docs[name]=json.loads(blob)
    report=docs['report.json']; graph=docs['graph.json']
    if run_id!='ae16-'+sha(canonical({'schema':SEAL_SCHEMA,'report':report,'graph':graph}))[:28]:
        raise ValueError('Operational generation identity does not match contents')
    budgets=report.get('bounds',{})
    expected_report,expected_graph=build_report(declaration,evidence_root,ae01_output=ae01_output,
                                                 source_root=source_root,
                                                 max_ae09_candidates=budgets['max_ae09_candidates'])
    if report!=expected_report or graph!=expected_graph:
        raise ValueError('Operational report disagrees with independently replayed input')
    if report.get('verified_findings')!=[] or report.get('source_authority')!='untrusted_execution_declaration_not_github_authenticated':
        raise ValueError('Operational observations have been promoted to findings')
    return {'generation':run_id,'assurance':report['assurance'],'issues':len(report['issues']),
            'required_checks':report['coverage_summary']['required'],
            'observed_pass_claims':report['coverage_summary']['observed_pass_claims'],
            'verification':'independent_replay_of_supplied_evidence_not_authenticated_execution'}
