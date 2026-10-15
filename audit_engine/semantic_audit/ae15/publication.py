"""AE-15 source-replayable, sealed observation publication; never G3 findings.

Reuses AE-01 atomic and locking helpers, but cannot use AE-01's finding
publisher/verification schema because AE-15 explicitly makes no finding claim.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path

from audit_engine.semantic_audit.ae01.publication import (
    _atomic_bytes, _fsync_dir, _no_symlink_components, attempt, canonical, sha,
)
from audit_engine.semantic_audit.ae01.source import inventory, EXCLUDE_DIRS
from audit_engine.semantic_audit.core.semantic_graph import SemanticGraph
from audit_engine.semantic_audit.graph.analysis.identity import graph_fingerprint
from .flow import analyze_snapshot, VERSION

SEAL_SCHEMA = 'ae15/observation_seal/v1'


def _graph_document(graph: SemanticGraph) -> dict:
    return {
        'nodes': [{'id':n.node_id,'type':n.entity_type,'attributes':n.attributes,'metadata':n.metadata}
                  for n in graph.nodes],
        'edges': [{'source':e.source_id,'target':e.target_id,'relation':e.relation_type,
                   'attributes':e.attributes,'metadata':e.metadata} for e in graph.edges],
    }


def _validate_paths(source_root: Path, output_root: Path):
    source_root = Path(os.path.abspath(source_root))
    output_root = Path(os.path.abspath(output_root))
    if source_root == output_root or source_root in output_root.parents:
        raise ValueError('AE-15 observation output must be outside its source tree')
    _no_symlink_components(source_root)
    _no_symlink_components(output_root)
    if not source_root.is_dir():
        raise ValueError('Source root is not a directory')
    return source_root, output_root


def audit_flow_repository(source_root: Path, output_root: Path, *, excludes: tuple[str,...]=(),
                          max_points_per_scope: int=3000,max_iterations: int=5000,
                          max_total_points: int=30000) -> dict:
    source_root,output_root=_validate_paths(Path(source_root),Path(output_root))
    with attempt(output_root):
        manifest,sources=inventory(source_root,excludes=excludes)
        if manifest['summary']['error'] or not sources:
            raise ValueError('AE-15 source inventory incomplete or empty; no clean evidence')
        report,graph=analyze_snapshot(sources,manifest,max_points_per_scope=max_points_per_scope,
                                     max_iterations=max_iterations,max_total_points=max_total_points)
        again,second=inventory(source_root,excludes=excludes)
        if manifest != again or sources!=second:
            raise ValueError('Source changed during AE-15 analysis')
        report={**report,'evidence_status':'unverified_observation',
                'assurance_claim':'NO_VERIFIED_FINDINGS_OR_RUNTIME_PROOF',
                'analysis_budgets':{'max_points_per_scope':max_points_per_scope,
                                    'max_iterations':max_iterations,'max_total_points':max_total_points}}
        artifacts={'manifest.json':manifest,'flow_report.json':report,'graph.json':_graph_document(graph)}
        data={name:canonical(value) for name,value in artifacts.items()}
        run_id='ae15-'+sha(canonical({'schema':VERSION,'source':report['sources'],
                                     'graph':report['graph_fingerprint'],
                                     'budgets':[max_points_per_scope,max_iterations,max_total_points]}))[:28]
        generations=output_root/'generations'
        generations.mkdir(exist_ok=True)
        _no_symlink_components(generations)
        stage=Path(tempfile.mkdtemp(prefix='.ae15-staging-',dir=generations))
        try:
            for name,raw in data.items():_atomic_bytes(stage/name,raw)
            seal=canonical({'schema':SEAL_SCHEMA,'artifacts':{name:sha(raw) for name,raw in data.items()}})
            _atomic_bytes(stage/'SEAL.json',seal)
            final=generations/run_id
            if final.exists() or final.is_symlink():
                _no_symlink_components(final)
                if not final.is_dir() or set(p.name for p in final.iterdir()) != set(data)|{'SEAL.json'}:
                    raise ValueError('Existing generation membership mismatch')
                for name,raw in data.items():
                    _no_symlink_components(final/name)
                    if (final/name).read_bytes()!=raw:raise ValueError('Existing generation content conflict')
                if (final/'SEAL.json').read_bytes()!=seal:raise ValueError('Existing generation seal conflict')
            else:
                os.rename(stage,final)
                _fsync_dir(generations)
            _atomic_bytes(output_root/'LATEST.json',canonical({'status':'completed',
                         'generation':run_id,'seal_sha256':sha(seal)}))
        finally:
            if stage.exists():shutil.rmtree(stage)
    return verify_flow_repository(source_root,output_root)


def verify_flow_repository(source_root: Path,output_root: Path) -> dict:
    """Independent source-byte replay and graph/fact comparison, not verifier receipt."""
    source_root,output_root=_validate_paths(Path(source_root),Path(output_root))
    latest_path=output_root/'LATEST.json'
    _no_symlink_components(latest_path)
    latest=json.loads(latest_path.read_bytes())
    if latest.get('status')!='completed':raise ValueError('Last AE-15 attempt not complete')
    run_id=latest.get('generation','')
    if not isinstance(run_id,str) or not run_id.startswith('ae15-') or len(run_id)!=33 or not all(c in '0123456789abcdef' for c in run_id[5:]):
        raise ValueError('Malformed AE-15 generation ID')
    root=output_root/'generations'/run_id
    _no_symlink_components(root)
    if not root.is_dir():raise ValueError('Missing AE-15 generation')
    expected_names={'manifest.json','flow_report.json','graph.json','SEAL.json'}
    if set(p.name for p in root.iterdir())!=expected_names:raise ValueError('Unexpected evidence artifact membership')
    for name in expected_names:_no_symlink_components(root/name)
    seal_data=(root/'SEAL.json').read_bytes()
    if sha(seal_data)!=latest.get('seal_sha256'):raise ValueError('AE-15 seal checksum mismatch')
    seal=json.loads(seal_data)
    if seal.get('schema')!=SEAL_SCHEMA or set(seal.get('artifacts',{}))!=expected_names-{'SEAL.json'}:
        raise ValueError('Invalid AE-15 seal')
    documents={}
    for name,h in seal['artifacts'].items():
        blob=(root/name).read_bytes()
        if sha(blob)!=h:raise ValueError(f'AE-15 artifact checksum mismatch: {name}')
        documents[name]=json.loads(blob)
    manifest,report,graphdoc=(documents['manifest.json'],documents['flow_report.json'],documents['graph.json'])
    conf=tuple(sorted(set(manifest.get('exclusions',[]))-set(EXCLUDE_DIRS)))
    refreshed,sources=inventory(source_root,excludes=conf)
    if refreshed!=manifest:raise ValueError('AE-15 source changed since publication')
    expected_report,expected_graph=analyze_snapshot(sources,manifest,**report['analysis_budgets'])
    expected_id='ae15-'+sha(canonical({'schema':VERSION,'source':expected_report['sources'],
                                     'graph':expected_report['graph_fingerprint'],
                                     'budgets':[report['analysis_budgets'][key] for key in
                                     ('max_points_per_scope','max_iterations','max_total_points')]}))[:28]
    if run_id!=expected_id:raise ValueError('AE-15 generation identity mismatch')
    # The graph and semantic facts are replayed using the published schema, not
    # accepted merely because a caller supplied a self-consistent hash.
    if {key:report[key] for key in expected_report}!=expected_report:
        raise ValueError('AE-15 semantics changed or report forged')
    if (report.get('evidence_status')!='unverified_observation' or
        report.get('assurance_claim')!='NO_VERIFIED_FINDINGS_OR_RUNTIME_PROOF'):
        raise ValueError('AE-15 observation promoted without authorization')
    if graphdoc!=_graph_document(expected_graph):raise ValueError('AE-15 graph replay mismatch')
    if graph_fingerprint(expected_graph)!=report['graph_fingerprint']:
        raise ValueError('AE-15 graph fingerprint mismatch')
    return {'generation':run_id,'graph_fingerprint':report['graph_fingerprint'],
            'assurance':report['assurance'],'scope_count':len(report['scopes']),
            'evidence_status':report['evidence_status'],'verification':'source_replayed_observations_only'}
