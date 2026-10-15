"""Sealed independent replay of the fixed-label operational evaluation."""
from __future__ import annotations
import json
import os
import shutil
import tempfile
from pathlib import Path
from audit_engine.semantic_audit.ae01.publication import (
    _atomic_bytes,_fsync_dir,_no_symlink_components,attempt,canonical,sha
)
from .evaluate import SCHEMA, evaluate_corpus

SEAL_SCHEMA='ae18/effectiveness_seal/v1'
MEMBERS={'evaluation.json','SEAL.json'}

def _roots(corpus_root,output_root):
    corpus=Path(os.path.abspath(corpus_root));output=Path(os.path.abspath(output_root))
    _no_symlink_components(corpus);_no_symlink_components(output)
    if corpus==output or corpus in output.parents or output in corpus.parents:
        raise ValueError('Evaluation output may not overlap reference corpus')
    return corpus,output

def publish_evaluation(corpus_root,output_root):
    corpus,output=_roots(corpus_root,output_root)
    with attempt(output):
        report=evaluate_corpus(corpus)
        if report!=evaluate_corpus(corpus):
            raise ValueError('Reference corpus or evaluation changed during publication')
        blob=canonical(report)
        if len(blob)>3_000_000:raise ValueError('Evaluation report exceeds byte budget')
        seal=canonical({'schema':SEAL_SCHEMA,'artifacts':{'evaluation.json':sha(blob)}})
        generation='ae18-'+sha(canonical({'schema':SEAL_SCHEMA,'report':report}))[:28]
        generations=output/'generations';generations.mkdir(exist_ok=True)
        _no_symlink_components(generations)
        stage=Path(tempfile.mkdtemp(prefix='.ae18-stage-',dir=generations))
        try:
            _atomic_bytes(stage/'evaluation.json',blob)
            _atomic_bytes(stage/'SEAL.json',seal)
            final=generations/generation
            if final.exists() or final.is_symlink():
                _no_symlink_components(final)
                if not final.is_dir() or {f.name for f in final.iterdir()}!=MEMBERS:
                    raise ValueError('Existing evaluation generation membership mismatch')
                for name,data in (('evaluation.json',blob),('SEAL.json',seal)):
                    _no_symlink_components(final/name)
                    if (final/name).read_bytes()!=data:raise ValueError('Existing evaluation generation altered')
            else:
                os.rename(stage,final);_fsync_dir(generations)
            _atomic_bytes(output/'LATEST.json',canonical({'status':'completed','generation':generation,'seal_sha256':sha(seal)}))
        finally:
            if stage.exists():shutil.rmtree(stage)
    return verify_evaluation(corpus,output)

def verify_evaluation(corpus_root,output_root):
    corpus,output=_roots(corpus_root,output_root)
    pointer=_read_json(output/'LATEST.json',8192)
    if set(pointer)!={'status','generation','seal_sha256'} or pointer['status']!='completed':
        raise ValueError('Evaluation last attempt not complete')
    generation=pointer['generation']
    if not isinstance(generation,str) or len(generation)!=33 or not generation.startswith('ae18-') or any(c not in '0123456789abcdef' for c in generation[5:]):
        raise ValueError('Invalid evaluation generation identity')
    folder=output/'generations'/generation
    _no_symlink_components(folder)
    if not folder.is_dir() or {f.name for f in folder.iterdir()}!=MEMBERS:
        raise ValueError('Evaluation artifacts missing or unexpected')
    seal=_read_json(folder/'SEAL.json',8192)
    if set(seal)!={'schema','artifacts'} or seal['schema']!=SEAL_SCHEMA or set(seal['artifacts'])!={'evaluation.json'}:
        raise ValueError('Unsupported evaluation seal')
    if sha((folder/'SEAL.json').read_bytes())!=pointer['seal_sha256']:
        raise ValueError('Evaluation seal digest mismatch')
    report=_read_json(folder/'evaluation.json',3_000_000)
    if sha((folder/'evaluation.json').read_bytes())!=seal['artifacts']['evaluation.json']:
        raise ValueError('Evaluation content digest mismatch')
    if generation!='ae18-'+sha(canonical({'schema':SEAL_SCHEMA,'report':report}))[:28]:
        raise ValueError('Evaluation generation identity mismatch')
    if report.get('schema')!=SCHEMA or report.get('verified_findings')!=[] or report.get('verified_root_causes')!=[]:
        raise ValueError('Unauthorized elevation of reference evaluation to verified finding')
    if report!=evaluate_corpus(corpus):
        raise ValueError('Evaluation does not match independent source replay')
    return {'generation':generation,'candidate_gate':report['candidate_gate'],
            'metrics':report['metrics'],'assurance':'source_replayed_controlled_reference_not_external_effectiveness_proof'}

def _read_json(path:Path,limit:int)->dict:
    _no_symlink_components(path)
    if not path.is_file() or path.stat().st_size>limit:raise ValueError('Evaluation artifact missing or oversized')
    blob=path.read_bytes()
    doc=json.loads(blob)
    if not isinstance(doc,dict) or canonical(doc)!=blob:
        raise ValueError('Evaluation artifact not canonical')
    return doc
