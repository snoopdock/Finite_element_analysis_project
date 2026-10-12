"""G4 RDF export executable tests: syntax, provenance, multiplicity and safety."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from audit_engine.semantic_audit.core.semantic_graph import SemanticGraph, SemanticNode, SemanticEdge
from audit_engine.semantic_audit.graph.domain_integration import GraphDomainView, from_scientific_graph
from audit_engine.semantic_audit.graph.persistent_domain_state import PersistentDomainGraphStore, canonical
from audit_engine.semantic_audit.graph.rdf_export import (
    RDFExportError, RDF, _iri, export_view, verify_export,
    export_to_directory, read_export, _json_literal,
)


ROOT = Path(__file__).resolve().parents[2]


def graph_view(reverse=False):
    graph = SemanticGraph()
    nodes = [SemanticNode('a / Δ \\"', 'ScienceConcept', {'name': 'α β', 'nested': {'a': 1}}, {'verified': False}),
             SemanticNode('b', 'Equation', {'expression': 'x\\ny'}, {})]
    edges = [SemanticEdge('a / Δ \\"', 'b', 'DEPENDS_ON', {'weight': 1}, {'evidence': 'unverified'}),
             SemanticEdge('a / Δ \\"', 'b', 'DEPENDS_ON', {'weight': 1}, {'evidence': 'unverified'}),
             SemanticEdge('b', 'b', 'SELF_LINK', {}, {})]
    for item in (reversed(nodes) if reverse else nodes):
        graph.add_node(item)
    for item in (reversed(edges) if reverse else edges):
        graph.add_edge(item)
    return GraphDomainView(graph, 'scientific_knowledge', 'a'*64)


def test_export_determinism_and_insertion_order():
    one = export_view(graph_view())
    two = export_view(graph_view(reverse=True))
    assert one == two
    assert one['ntriples'].endswith(b'\n')
    assert one['turtle'].startswith(b'@prefix fea:')
    assert one['manifest']['node_count'] == 2
    assert one['manifest']['edge_occurrence_count'] == 3


def test_reified_parallel_edges_retained():
    result = export_view(graph_view())
    lines = result['ntriples'].decode().splitlines()
    predicate = _iri('property:containsEdge')
    assert sum(f' {predicate} ' in line for line in lines) == 3
    assert sum(f' <{RDF}Statement> ' in line for line in lines) == 3
    assert sum(f' {_iri("relation:DEPENDS_ON")} ' in line and line.endswith(f' {_iri("node:b")} .') for line in lines) == 1
    assert any('parallelEdgeOccurrence' in line and '"1"' in line for line in lines)


def test_semantic_boundaries_are_explicit_false():
    raw = export_view(graph_view())['ntriples'].decode()
    assert 'scientificTruthEstablished' in raw
    assert 'automaticApprovalPermitted' in raw
    assert 'authoritativeMutationPermitted' in raw
    assert '"false"^^<http://www.w3.org/2001/XMLSchema#boolean>' in raw
    assert export_view(graph_view())['manifest']['rdf_semantic_entailment_verified'] is False


def test_export_immutable_from_caller_perspective():
    view = graph_view()
    before = copy.deepcopy(view.graph.to_dict())
    export_view(view)
    assert view.graph.to_dict() == before


@pytest.mark.parametrize('which', ['ntriples', 'turtle', 'manifest'])
def test_independent_verification_rejects_modified_bundle(which):
    view = graph_view()
    bundle = export_view(view)
    assert verify_export(view, bundle)
    tampered = dict(bundle)
    if which == 'manifest':
        tampered[which] = dict(tampered[which], automatic_approval_permitted=True)
    else:
        tampered[which] += b'\n'
    with pytest.raises(RDFExportError):
        verify_export(view, tampered)


def test_graph_input_validation_rejects_dangling_edge():
    view = graph_view()
    view.graph.edges.append(SemanticEdge('ghost', 'b', 'DEPENDS_ON'))
    with pytest.raises((ValueError, RDFExportError)):
        export_view(view)


def test_metadata_must_be_finite_json():
    view = graph_view()
    view.graph.nodes[0].metadata['confidence'] = float('nan')
    with pytest.raises((ValueError, RDFExportError)):
        export_view(view)


def test_invalid_resource_identifier_is_rejected():
    view = graph_view()
    view.graph.nodes[0].node_id = ''
    with pytest.raises((ValueError, RDFExportError)):
        export_view(view)


def test_literal_escaping_and_unicode():
    literal = _json_literal({'text': 'Ω " quote\nbackslash\\', 'b': True})
    assert '\\n' in literal
    assert '\\"' in literal
    assert '\\\\' in literal


def test_store_state_binding_rejects_false_receipt():
    view = graph_view()
    snapshot = view.snapshot()
    state = {'status': 'verified', 'head': '0'*64, 'generation': 1,
             'snapshot_sha256': snapshot['snapshot_sha256'], 'graph_fingerprint': view.fingerprint}
    assert export_view(view, store_state=state)['manifest']['persisted_store_head'] == '0'*64
    for key, value in [('head', None), ('generation', None), ('graph_fingerprint', 'bad'),
                       ('snapshot_sha256', 'bad'), ('status', 'empty')]:
        broken = dict(state, **{key: value})
        with pytest.raises(RDFExportError):
            export_view(view, store_state=broken)


def test_candidate_cli_from_existing_ge02_demo(tmp_path):
    output = tmp_path/'rdf'
    manifest = export_to_directory(ROOT, output, mode='candidate',
                                   knowledge_graph='examples/graph_engine/ge02_demo_graph.json')
    assert manifest['node_count'] == 3
    assert manifest['edge_occurrence_count'] == 2
    assert read_export(output)['manifest'] == manifest
    assert hashlib.sha256((output/'semantic-graph.nt').read_bytes()).hexdigest() == manifest['ntriples_sha256']


def test_candidate_output_must_not_write_into_repository(tmp_path):
    with pytest.raises(RDFExportError):
        export_to_directory(ROOT, ROOT/'g4-new-output-forbidden', mode='candidate',
                            knowledge_graph='examples/graph_engine/ge02_demo_graph.json')


def test_existing_output_rejected_before_write(tmp_path):
    output = tmp_path/'rdf'
    output.mkdir()
    with pytest.raises(RDFExportError):
        export_to_directory(ROOT, output, mode='candidate',
                            knowledge_graph='examples/graph_engine/ge02_demo_graph.json')


def test_missing_candidate_is_rejected(tmp_path):
    with pytest.raises(RDFExportError):
        export_to_directory(ROOT, tmp_path/'rdf', mode='candidate', knowledge_graph='examples/graph_engine/not-here.json')


def test_traversal_input_rejected(tmp_path):
    with pytest.raises(RDFExportError):
        export_to_directory(ROOT, tmp_path/'rdf', mode='candidate', knowledge_graph='../secrets.json')


def test_candidate_invalid_graph_rejected(tmp_path):
    repo = tmp_path/'repo'
    repo.mkdir()
    (repo/'bad.json').write_text('{"concepts":{"a":{"concept_id":"a"}}}', encoding='utf-8')
    with pytest.raises(RDFExportError):
        export_to_directory(repo, tmp_path/'rdf', mode='candidate', knowledge_graph='bad.json')


def test_persisted_graph_export_checks_ge02_history(tmp_path):
    # Actual shipped GE-02 state from the current repository (not an invented latest.json).
    manifest = export_to_directory(ROOT, tmp_path/'rdf', mode='persisted')
    assert manifest['persisted_store_generation'] >= 1
    assert manifest['persisted_store_head'] == PersistentDomainGraphStore(ROOT/'.graph-state/scientific').verify()['head']


def test_empty_persisted_store_rejected(tmp_path):
    repo = tmp_path/'repo'
    (repo/'.graph-state/scientific').mkdir(parents=True)
    with pytest.raises(RDFExportError):
        export_to_directory(repo, tmp_path/'rdf', mode='persisted')


def test_corrupted_persisted_head_rejected(tmp_path):
    repo = tmp_path/'repo'
    store = repo/'.graph-state/scientific'
    store.mkdir(parents=True)
    (store/'HEAD.json').write_text('{}')
    with pytest.raises((ValueError, RDFExportError)):
        export_to_directory(repo, tmp_path/'rdf', mode='persisted')


def test_read_export_rejects_symlink(tmp_path):
    output = tmp_path/'rdf'
    export_to_directory(ROOT, output, mode='candidate', knowledge_graph='examples/graph_engine/ge02_demo_graph.json')
    f = output/'semantic-graph.nt'
    backup = tmp_path/'backup.nt'
    f.rename(backup)
    f.symlink_to(backup)
    with pytest.raises(RDFExportError):
        read_export(output)


def test_cli_can_export_to_new_external_directory(tmp_path):
    cmd = [sys.executable, '-m', 'audit_engine.semantic_audit.graph.rdf_export',
           '--repository', str(ROOT), '--mode', 'persisted', '--output-dir', str(tmp_path/'output')]
    p = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, timeout=15)
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout)['schema_version'] == 'g4-rdf-export/v1'


def test_export_rdf_parses_with_standard_parser_if_available():
    rdflib = pytest.importorskip('rdflib')
    bundle = export_view(graph_view())
    triples = rdflib.Graph().parse(data=bundle['ntriples'].decode(), format='nt')
    turtle = rdflib.Graph().parse(data=bundle['turtle'].decode(), format='turtle')
    assert len(triples) == len(turtle) == bundle['manifest']['triple_count']
    assert set(triples) == set(turtle)


def test_export_preserves_real_scientific_graph_relations():
    raw = json.loads((ROOT/'examples/graph_engine/ge02_demo_graph.json').read_text())
    view = from_scientific_graph(raw)
    bundle = export_view(view)
    text = bundle['ntriples'].decode()
    assert 'relation%3ASUBCONCEPT_OF' in text
    assert 'relation%3AHAS_CONCEPT' in text
    assert bundle['manifest']['edge_occurrence_count'] == 2
