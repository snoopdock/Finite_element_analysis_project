"""GE-01 substantive identity, provenance, audit-handoff, and existing-query tests."""
from __future__ import annotations

import copy
import hashlib
import json
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from audit_engine.semantic_audit.graph.domain_integration import (
    GraphDomainError, combine_views, from_scientific_graph,
    from_verified_assurance_cycle, verify_snapshot,
)
from audit_engine.semantic_audit.graph.analysis import GraphTraversalEngine, TraversalDirection
from audit_engine.semantic_audit.graph.queries import GraphQuery, QueryType

ROOT = Path(__file__).resolve().parents[2]
A = str(uuid.UUID(int=1)); B = str(uuid.UUID(int=2)); P = str(uuid.UUID(int=3)); R = str(uuid.UUID(int=4))


@pytest.fixture
def science():
    return {
        'concepts': {
            A: {'concept_id': A, 'name': 'Finite elements', 'type': 'method',
                'parent_concept_ids': [], 'source_ids': ['doi:10.demo/a']},
            B: {'concept_id': B, 'name': 'Galerkin method', 'type': 'method',
                'parent_concept_ids': [A], 'source_ids': ['doi:10.demo/a']},
        },
        'propositions': {
            P: {'proposition_id': P, 'statement': 'Galerkin has weighted residual interpretation',
                'concept_ids': [B], 'status': 'proposed', 'source_ids': ['doi:10.demo/a']},
        },
        'relationships': {
            R: {'relationship_id': R, 'source_id': B, 'target_id': A,
                'type': 'depends_on', 'status': 'proposed',
                'proposition_ids': [P], 'source_ids': ['doi:10.demo/a']},
        },
    }


def test_existing_canonical_graph_reused(science):
    from audit_engine.semantic_audit.core.semantic_graph import SemanticGraph
    view = from_scientific_graph(science)
    assert isinstance(view.graph, SemanticGraph)
    assert len(view.graph.nodes) == 4
    assert len(view.graph.edges) == 7


def test_proposition_preserves_unverified_status(science):
    node = from_scientific_graph(science).graph.get_node('scientific:proposition:' + P)
    assert node.attributes['status'] == 'proposed'
    assert node.metadata['scientific_truth_established'] is False


def test_scientific_sources_are_not_verified(science):
    graph = from_scientific_graph(science).graph
    source = next(n for n in graph.nodes if n.entity_type == 'ScientificSourceRef')
    assert not source.metadata['source_verified']
    assert source.attributes['source_id_unverified'] == 'doi:10.demo/a'


def test_science_identity_independent_of_insertion_order(science):
    other = copy.deepcopy(science)
    other['concepts'] = dict(reversed(list(other['concepts'].items())))
    assert from_scientific_graph(other).fingerprint == from_scientific_graph(science).fingerprint
    assert from_scientific_graph(other).snapshot() == from_scientific_graph(science).snapshot()


def test_change_source_updates_content_hash(science):
    original = from_scientific_graph(science)
    science['propositions'][P]['source_ids'].append('doi:10.demo/b')
    other = from_scientific_graph(science)
    assert other.fingerprint != original.fingerprint
    assert other.input_sha256 != original.input_sha256


def test_input_never_modified(science):
    before = copy.deepcopy(science)
    from_scientific_graph(science)
    assert science == before


def test_graph_copies_records(science):
    view = from_scientific_graph(science)
    science['concepts'][A]['name'] = 'tampered'
    assert view.graph.get_node('scientific:concept:'+A).attributes['name'] == 'Finite elements'


def test_reference_hierarchy_path_in_existing_graph_engine(science):
    view = from_scientific_graph(science)
    traversal = GraphTraversalEngine(view.graph).walk('scientific:concept:'+B,
                                                       relation_types=['SUBCONCEPT_OF'], max_depth=1)
    assert 'scientific:concept:'+A in traversal.visited_nodes


def test_existing_analysis_service(science):
    query = GraphQuery('ge01-q', QueryType.DEPENDENCY, ['scientific:proposition:'+P],
                       {'relation_types': ['HAS_CONCEPT'], 'max_depth': 1})
    result = from_scientific_graph(science).analyze(query)
    assert result.query_id == 'ge01-q'
    assert result.graph_fingerprint


def test_snapshot_integrity_against_rehashed_tamper(science):
    view = from_scientific_graph(science)
    snap = view.snapshot()
    assert verify_snapshot(view, snap)
    snap['graph']['nodes'][0]['type'] = 'AuthoritativeTruth'
    snap['snapshot_sha256'] = hashlib.sha256(json.dumps({k:v for k,v in snap.items() if k!='snapshot_sha256'},
                                                        sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
    with pytest.raises(GraphDomainError):verify_snapshot(view,snap)


@pytest.mark.parametrize('change', [
    lambda x: x['concepts'][B].update({'parent_concept_ids':[str(uuid.UUID(int=33))]}),
    lambda x: x['propositions'][P].update({'concept_ids':[str(uuid.UUID(int=33))]}),
    lambda x: x['relationships'][R].update({'target_id': str(uuid.UUID(int=33))}),
    lambda x: x['relationships'][R].update({'proposition_ids':[str(uuid.UUID(int=33))]}),
    lambda x: x['concepts'][B].update({'parent_concept_ids':[B]}),
])
def test_reject_dangling_or_recursive_refs(science,change):
    change(science)
    with pytest.raises(GraphDomainError):from_scientific_graph(science)


def test_reject_identity_disagreement(science):
    science['concepts'][A]['concept_id'] = B
    with pytest.raises(GraphDomainError):from_scientific_graph(science)


def test_reject_bad_uuid(science):
    science['propositions']['arbitrary'] = science['propositions'].pop(P)
    with pytest.raises(GraphDomainError):from_scientific_graph(science)


def test_reject_repeated_source_reference(science):
    science['propositions'][P]['source_ids'] = ['dup', 'dup']
    with pytest.raises(GraphDomainError):from_scientific_graph(science)


def test_reject_nonfinite_confidence(science):
    science['relationships'][R]['confidence'] = float('nan')
    with pytest.raises(GraphDomainError):from_scientific_graph(science)


def test_no_implicit_cross_domain_merge(science):
    a=from_scientific_graph(science)
    with pytest.raises(GraphDomainError):combine_views(a,a)


def test_combined_single_view_is_read_only(science):
    v=from_scientific_graph(science)
    combined=combine_views(v)
    assert combined.snapshot()['authoritative_mutation_permitted'] is False
    assert combined.fingerprint == v.fingerprint


def test_legacy_core_reference_validator_is_not_mutated(science):
    from core.knowledge_graph import validate_graph_references
    assert validate_graph_references(science) == []
    assert validate_graph_references(science) == []


@pytest.fixture
def checked_repo(tmp_path):
    from decision_memory import assurance_integration
    if not (ROOT/'decision_memory').is_dir():
        pytest.skip('G3.5 branch unavailable')
    dst=tmp_path/'source'
    dst.mkdir()
    shutil.copytree(ROOT/'decision_memory',dst/'decision_memory',ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copytree(ROOT/'validation',dst/'validation',ignore=shutil.ignore_patterns('__pycache__'))
    return dst


@pytest.fixture
def cycle(checked_repo):
    from decision_memory.assurance_integration import create_cycle
    return create_cycle(checked_repo, 'engineering validation',
                        'Review engineering reasoning [[DEC-G3.4.13-001]]')


def test_real_g35_projection(checked_repo,cycle):
    view=from_verified_assurance_cycle(cycle,checked_repo)
    assert view.domain == 'generated_text_audit'
    assert any(e.relation_type == 'CITES_STRUCTURALLY' for e in view.graph.edges)
    assert not view.snapshot()['scientific_truth_established']


def test_projected_claim_is_untrusted(checked_repo,cycle):
    view=from_verified_assurance_cycle(cycle,checked_repo)
    claim=next(n for n in view.graph.nodes if n.entity_type=='AuditGeneratedClaim')
    assert claim.metadata['scientific_support_verified'] is False


def test_g35_combines_with_scientific_graph(checked_repo,cycle,science):
    combined=combine_views(from_scientific_graph(science),from_verified_assurance_cycle(cycle,checked_repo))
    assert combined.domain=='combined_read_only'
    assert len(combined.graph.nodes) > 4
    assert not combined.snapshot()['authoritative_mutation_permitted']


def test_tampered_g35_edge_rejected_with_recomputed_digest(checked_repo,cycle):
    from decision_memory.assurance_integration import _digest
    cycle['graph_handoff']['edges'][0]['type'] = 'PROVES'
    cycle['cycle_sha256'] = _digest({k:v for k,v in cycle.items() if k!='cycle_sha256'})
    with pytest.raises(GraphDomainError):from_verified_assurance_cycle(cycle,checked_repo)


def test_tampered_g35_sources_rejected(checked_repo,cycle):
    src=checked_repo/'decision_memory/decisions/DEC-G3.4.13-001.yaml'
    src.write_text(src.read_text()+'\n# tamper\n')
    with pytest.raises(GraphDomainError):from_verified_assurance_cycle(cycle,checked_repo)


def test_g35_graph_does_not_accept_forged_authority(checked_repo,cycle):
    from decision_memory.assurance_integration import _digest
    cycle['graph_handoff']['authoritative_graph_mutation_permitted'] = True
    cycle['cycle_sha256'] = _digest({k:v for k,v in cycle.items() if k!='cycle_sha256'})
    with pytest.raises(GraphDomainError):from_verified_assurance_cycle(cycle,checked_repo)


def test_unverified_g35_cycle_rejected(checked_repo,cycle):
    cycle['draft_sha256']='0'*64
    with pytest.raises(GraphDomainError):from_verified_assurance_cycle(cycle,checked_repo)


def test_cli_scientific_snapshot_read_only(tmp_path,science):
    inp=tmp_path/'science.json';inp.write_text(json.dumps(science))
    root=tmp_path/'repo';root.mkdir()
    before=inp.read_bytes()
    out=tmp_path/'graph.json'
    cmd=[sys.executable,'-m','audit_engine.semantic_audit.graph.domain_integration',
         '--repository',str(root),'--knowledge-graph',str(inp),'--output',str(out)]
    proc=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,timeout=30)
    assert proc.returncode==0,proc.stderr
    assert json.loads(out.read_text())['schema_version']=='graph-domain-view/v1'
    assert inp.read_bytes()==before


def test_cli_reject_repository_write(tmp_path,science):
    inp=tmp_path/'science.json';inp.write_text(json.dumps(science))
    repo=tmp_path/'repo';repo.mkdir()
    out=repo/'graph.json'
    proc=subprocess.run([sys.executable,'-m','audit_engine.semantic_audit.graph.domain_integration',
         '--repository',str(repo),'--knowledge-graph',str(inp),'--output',str(out)],
        cwd=ROOT,capture_output=True,text=True,timeout=30)
    assert proc.returncode!=0
    assert not out.exists()


def test_cli_reject_duplicate_json_keys(tmp_path):
    from audit_engine.semantic_audit.graph.domain_integration import _read_json
    p=tmp_path/'bad.json';p.write_text('{"concepts": {}, "concepts": {}}')
    with pytest.raises(GraphDomainError):_read_json(p)


def test_cli_reject_symlinks(tmp_path):
    from audit_engine.semantic_audit.graph.domain_integration import _read_json
    p=tmp_path/'ok.json';p.write_text('{}');link=tmp_path/'link.json';link.symlink_to(p)
    with pytest.raises(GraphDomainError):_read_json(link)


def test_profile_contract():
    p=ROOT/'validation/profiles/G4.1.yaml'
    assert p.is_file()
    text=p.read_text()
    assert 'test_ge01_domain_integration.py' in text
    assert 'regression:' in text and 'enabled: true' in text


def test_cli_verified_cycle_uses_real_review_chain(tmp_path, checked_repo, cycle):
    p=tmp_path/'cycle.json';p.write_text(json.dumps(cycle))
    out=tmp_path/'graph.json'
    cmd=[sys.executable,'-m','audit_engine.semantic_audit.graph.domain_integration',
         '--repository',str(checked_repo),'--g35-cycle',str(p),'--output',str(out)]
    proc=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,timeout=40)
    assert proc.returncode==0,proc.stderr
    graph=json.loads(out.read_text())
    assert any(e['relation']=='CITES_STRUCTURALLY' for e in graph['graph']['edges'])
    assert not graph['authoritative_mutation_permitted']


def test_cli_both_graphs_and_no_cross_domain_join(tmp_path, checked_repo, cycle, science):
    path=tmp_path/'cycle.json';path.write_text(json.dumps(cycle))
    kg=tmp_path/'kg.json';kg.write_text(json.dumps(science))
    cmd=[sys.executable,'-m','audit_engine.semantic_audit.graph.domain_integration',
         '--repository',str(checked_repo),'--g35-cycle',str(path),'--knowledge-graph',str(kg)]
    proc=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,timeout=40)
    assert proc.returncode==0,proc.stderr
    graph=json.loads(proc.stdout)
    assert graph['domain']=='combined_read_only'
    assert all(n['id'].startswith(('scientific:', 'audit:')) for n in graph['graph']['nodes'])


def test_reject_oversized_input(tmp_path):
    from audit_engine.semantic_audit.graph.domain_integration import _read_json, MAX_BYTES
    p=tmp_path/'big.json';p.write_bytes(b'x'*(MAX_BYTES+1))
    with pytest.raises(GraphDomainError):_read_json(p)


def test_reject_nonfinite_json_literal(tmp_path):
    from audit_engine.semantic_audit.graph.domain_integration import _read_json
    p=tmp_path/'bad.json';p.write_text('{"foo":NaN}')
    with pytest.raises(GraphDomainError):_read_json(p)


def test_reject_empty_view_merge():
    with pytest.raises(GraphDomainError):combine_views()


def test_reject_bad_concept_collection():
    with pytest.raises(GraphDomainError):from_scientific_graph({'concepts': []})


def test_reject_source_as_string(science):
    science['concepts'][A]['source_ids']='doi:10.demo/a'
    with pytest.raises(GraphDomainError):from_scientific_graph(science)


def test_existing_destination_not_overwritten(tmp_path,science):
    inp=tmp_path/'science.json';inp.write_text(json.dumps(science))
    repo=tmp_path/'repo';repo.mkdir()
    out=tmp_path/'graph.json';out.write_text('KEEP')
    proc=subprocess.run([sys.executable,'-m','audit_engine.semantic_audit.graph.domain_integration',
        '--repository',str(repo),'--knowledge-graph',str(inp),'--output',str(out)],
        cwd=ROOT,capture_output=True,text=True,timeout=30)
    assert proc.returncode != 0
    assert out.read_text()=='KEEP'
