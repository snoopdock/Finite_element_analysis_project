"""Atomically publish and independently replay the AE-19 bounded casebook."""
from __future__ import annotations
import json
import os
import shutil
import tempfile
from pathlib import Path
from audit_engine.semantic_audit.ae01.publication import (
    _atomic_bytes,_fsync_dir,_no_symlink_components,attempt,canonical,sha
)
from .evaluate import evaluate_casebook,SCHEMA
SEAL_SCHEMA='ae19/history_seal/v1'
MEMBERS={'evaluation.json','SEAL.json'}


def _paths(corpus_root,output_root):
    corpus=Path(os.path.abspath(corpus_root));output=Path(os.path.abspath(output_root))
    _no_symlink_components(corpus);_no_symlink_components(output)
    if corpus==output or corpus in output.parents or output in corpus.parents:
        raise ValueError('Historical evaluation output may not overlap casebook')
    return corpus,output


def _read(path,limit):
    _no_symlink_components(path)
    if not path.is_file() or path.stat().st_size>limit:
        raise ValueError('Historical evaluation artifact missing or oversized')
    raw=path.read_bytes();obj=json.loads(raw)
    if not isinstance(obj,dict) or canonical(obj)!=raw:
        raise ValueError('Historical evaluation report is not canonical')
    return obj


def publish_casebook(corpus_root,output_root):
    corpus,output=_paths(corpus_root,output_root)
    with attempt(output):
        report=evaluate_casebook(corpus)
        if report!=evaluate_casebook(corpus):
            raise ValueError('Historical source bytes or evaluation changed during publication')
        blob=canonical(report)
        if len(blob)>3_000_000:raise ValueError('Historical report exceeds budget')
        seal=canonical({'schema':SEAL_SCHEMA,'artifacts':{'evaluation.json':sha(blob)}})
        generation='ae19-'+sha(canonical({'schema':SEAL_SCHEMA,'report':report}))[:28]
        generations=output/'generations';generations.mkdir(exist_ok=True)
        _no_symlink_components(generations)
        stage=Path(tempfile.mkdtemp(prefix='.ae19-stage-',dir=generations))
        try:
            _atomic_bytes(stage/'evaluation.json',blob)
            _atomic_bytes(stage/'SEAL.json',seal)
            final=generations/generation
            if final.exists() or final.is_symlink():
                _no_symlink_components(final)
                if not final.is_dir() or {f.name for f in final.iterdir()}!=MEMBERS:
                    raise ValueError('Existing historical generation members changed')
                for name,data in (('evaluation.json',blob),('SEAL.json',seal)):
                    _no_symlink_components(final/name)
                    if (final/name).read_bytes()!=data:
                        raise ValueError('Existing historical generation bytes changed')
            else:
                os.rename(stage,final);_fsync_dir(generations)
            _atomic_bytes(output/'LATEST.json',canonical({'status':'completed','generation':generation,'seal_sha256':sha(seal)}))
        finally:
            if stage.exists():shutil.rmtree(stage)
    return verify_casebook(corpus,output)


def verify_casebook(corpus_root,output_root):
    corpus,output=_paths(corpus_root,output_root)
    pointer=_read(output/'LATEST.json',8192)
    if set(pointer)!={'status','generation','seal_sha256'} or pointer['status']!='completed':
        raise ValueError('Last historical attempt is incomplete')
    generation=pointer['generation']
    if (not isinstance(generation,str) or len(generation)!=33 or not generation.startswith('ae19-')
        or any(x not in '0123456789abcdef' for x in generation[5:])):
        raise ValueError('Invalid historical generation identifier')
    folder=output/'generations'/generation
    _no_symlink_components(folder)
    if not folder.is_dir() or {f.name for f in folder.iterdir()}!=MEMBERS:
        raise ValueError('Historical generation membership mismatch')
    seal=_read(folder/'SEAL.json',8192)
    if (set(seal)!={'schema','artifacts'} or seal['schema']!=SEAL_SCHEMA or
        seal['artifacts'].keys()!={'evaluation.json'}):
        raise ValueError('Invalid historical seal')
    if sha((folder/'SEAL.json').read_bytes())!=pointer['seal_sha256']:
        raise ValueError('Historical seal digest mismatch')
    report=_read(folder/'evaluation.json',3_000_000)
    if sha((folder/'evaluation.json').read_bytes())!=seal['artifacts']['evaluation.json']:
        raise ValueError('Historical report digest mismatch')
    if generation!='ae19-'+sha(canonical({'schema':SEAL_SCHEMA,'report':report}))[:28]:
        raise ValueError('Historical generation hash mismatch')
    if report.get('schema')!=SCHEMA or report.get('verified_findings')!=[] or report.get('verified_root_causes')!=[]:
        raise ValueError('Unauthorized root-cause or finding promotion')
    if report!=evaluate_casebook(corpus):
        raise ValueError('Historical report does not match source replay')
    return {'generation':generation,'candidate_gate':report['candidate_gate'],
            'case_count':report['case_count'], 'exact_manual_case_matches':report['exact_manual_case_matches'],
            'assurance':'source_replayed_historical_step_logs_not_authenticated_run_or_causal_proof'}
