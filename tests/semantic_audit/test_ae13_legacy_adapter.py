import copy
import json
from pathlib import Path
import pytest
from audit_engine.semantic_audit.ae13 import adapt_legacy,validate_legacy_report
from audit_engine.semantic_audit.ae13.admission import validate_graph
from audit_engine.semantic_audit.core.semantic_graph import SemanticGraph,SemanticNode,SemanticEdge


def test_real_legacy_classifier_retains_observation_not_finding(tmp_path):
    (tmp_path/'alpha.py').write_text('import research.evidence\nfrom . import helper\nretrieval()\n',encoding='utf-8')
    report=adapt_legacy(tmp_path)
    assert validate_legacy_report(report,tmp_path)
    assert report['findings']==[]
    assert report['compatibility']['promoted_verified_findings']==0
    assert all(o['epistemic_status']=='observed' and o['verification_status']=='not_verified' for o in report['observations'])
    assert any(c['classification']=='SCIENTIFIC_READ_ACCESS' for o in report['observations'] if o['kind']=='import' for c in o['payload']['classifications'])
    assert any('empty_module_or_relative_import_level_lost' in o['uncertainty'] for o in report['observations'])
    assert report['graph_admission']['nodes']>1


def test_replay_rejects_source_change_or_rehashed_forgery(tmp_path):
    p=tmp_path/'f.py';p.write_text('import os\n')
    original=adapt_legacy(tmp_path)
    p.write_text('import subprocess\n')
    with pytest.raises(ValueError): validate_legacy_report(original,tmp_path)
    altered=copy.deepcopy(original);altered['observations'][0]['verification_status']='validated'
    from audit_engine.semantic_audit.ae13.identity import digest
    altered['report_sha256']=digest({k:v for k,v in altered.items() if k!='report_sha256'})
    with pytest.raises(ValueError): validate_legacy_report(altered,tmp_path)


def test_source_overwrite_symlink_and_traversal_rejected(tmp_path):
    q=tmp_path/'ok.py';q.write_text('import x\n')
    outside=tmp_path.parent/'ae13-never-read.py';
    for name in ('../ae13-never-read.py','/etc/passwd','ok.py/../ok.py'):
        with pytest.raises(ValueError):adapt_legacy(tmp_path,selected_paths=(name,))
    sy=tmp_path/'bad.py';sy.symlink_to(q)
    with pytest.raises(ValueError):adapt_legacy(tmp_path,selected_paths=('bad.py',))


def test_parse_failure_incomplete_not_clean(tmp_path):
    (tmp_path/'bad.py').write_text('def broken(:\n')
    r=adapt_legacy(tmp_path)
    assert r['assurance_status']=='incomplete' and len(r['issues'])==1
    assert validate_legacy_report(r,tmp_path)


def test_utf8_boundary_and_budgets(tmp_path):
    (tmp_path/'bad.py').write_bytes(b'\xff\x80')
    assert adapt_legacy(tmp_path)['assurance_status']=='incomplete'
    (tmp_path/'bad.py').write_bytes(b'x'*2000001)
    with pytest.raises(ValueError):adapt_legacy(tmp_path)


def test_duplicate_and_dangling_graph_detected():
    g=SemanticGraph();g.add_node(SemanticNode('n','Module'))
    g.nodes.append(SemanticNode('n','Module'))
    with pytest.raises(ValueError): validate_graph(g)
    g.nodes.pop()
    g.edges.append(SemanticEdge('n','missing','IMPORTS'))
    with pytest.raises(ValueError):validate_graph(g)


def test_identical_edge_occurrences_require_separate_ids():
    g=SemanticGraph();g.add_node(SemanticNode('n','N'))
    g.add_edge(SemanticEdge('n','n','REL',metadata={'ae13_occurrence_id':'one'}))
    g.add_edge(SemanticEdge('n','n','REL',metadata={'ae13_occurrence_id':'two'}))
    assert validate_graph(g)['edge_occurrences']==2
    g.edges[1].metadata['ae13_occurrence_id']='one'
    with pytest.raises(ValueError): validate_graph(g)


def test_deterministic_multiple_calls_same_line(tmp_path):
    (tmp_path/'a.py').write_text('f();f()\n')
    a=adapt_legacy(tmp_path);b=adapt_legacy(tmp_path)
    assert a==b and len(a['observations'])==2
    assert len({o['id'] for o in a['observations']})==2


def test_cli_legacy(tmp_path):
    import subprocess,sys
    (tmp_path/'ok.py').write_text('import os\n')
    p=subprocess.run([sys.executable,'-m','audit_engine.semantic_audit.ae13','legacy',str(tmp_path)],capture_output=True,text=True,check=True)
    assert json.loads(p.stdout)['assurance_status']=='source_bound_observations_only'


def test_symlinked_directory_not_omitted_silently(tmp_path):
    (tmp_path/'normal.py').write_text('import os\n')
    target=tmp_path/'target';target.mkdir();(target/'sub.py').write_text('import re\n')
    (tmp_path/'alias').symlink_to(target,target_is_directory=True)
    with pytest.raises(ValueError,match='Symlinked source directory'):
        adapt_legacy(tmp_path)
