"""G5.2 executable tests: source-bound RDFS axioms and separate finite structural checks."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest
from rdflib import Graph, Literal
from rdflib.namespace import RDF, RDFS, OWL, XSD

from audit_engine.semantic_audit.core.semantic_graph import SemanticGraph, SemanticNode, SemanticEdge
from audit_engine.semantic_audit.graph.domain_integration import GraphDomainView
from audit_engine.semantic_audit.graph.persistent_domain_state import PersistentDomainGraphStore, canonical
from audit_engine.semantic_audit.graph.rdf_export import export_view
from audit_engine.semantic_audit.graph.owl_ontology import build_owl_layer, ONTOLOGY, _iri, _prop
from audit_engine.semantic_audit.graph.owl_constraints import (
    OWLConstraintError, DECLARATIONS, SCHEMA, REPORT_SCHEMA,
    audit_structural_conformance, build_constraint_layer,
    verify_constraint_layer, write_constraint_directory,
    verify_constraint_directory, read_constraint_directory,
)

ROOT = Path(__file__).resolve().parents[2]


def make_view():
    g = SemanticGraph()
    g.add_node(SemanticNode('scientific:parent / α', 'ScientificConcept', {'name': 'elasticity'}, {}))
    g.add_node(SemanticNode('scientific:child', 'ScientificProposition', {'equation': 'f = ku'}, {}))
    g.add_node(SemanticNode('scientific:source', 'ScientificSourceRef', {}, {}))
    g.add_edge(SemanticEdge('scientific:parent / α', 'scientific:child', 'HAS_CONCEPT', {}, {}))
    g.add_edge(SemanticEdge('scientific:parent / α', 'scientific:child', 'HAS_CONCEPT', {}, {}))
    g.add_edge(SemanticEdge('scientific:child', 'scientific:child', 'SELF_LINK', {}, {}))
    return GraphDomainView(g, 'scientific_knowledge', 'f'*64)


@pytest.fixture
def source():
    view = make_view()
    rdf = export_view(view)
    g5 = build_owl_layer(view, rdf)
    bundle = build_constraint_layer(view, rdf, g5)
    return view, rdf, g5, bundle


def parse(bundle, key):
    return Graph().parse(data=bundle[key].decode('utf-8'), format='nt')


def test_valid_source_bound_roundtrip(source):
    view, rdf, g5, bundle = source
    assert verify_constraint_layer(view, rdf, g5, bundle) == bundle['manifest']
    assert bundle['manifest']['schema_version'] == SCHEMA
    assert bundle['manifest']['covered_node_count'] == 3
    assert bundle['manifest']['covered_edge_occurrence_count'] == 3


def test_declared_exact_profile(source):
    _, _, _, bundle = source
    g = parse(bundle, 'axioms_nt')
    for name, domain, rng in DECLARATIONS:
        prop = _iri('property', name)
        assert (prop, RDFS.range, rng) in g
        assert (prop, RDFS.domain, domain) in g if domain is not None else not list(g.objects(prop, RDFS.domain))
    assert (ONTOLOGY, _prop('constraintProfileSourceManifest'), None) in g


def test_15_constrained_properties(source):
    assert source[-1]['manifest']['constrained_property_count'] == 15


def test_literals_and_subclass_closure_conform(source):
    _, _, g5, _ = source
    parsed = parse(g5, 'combined_nt')
    result = audit_structural_conformance(parsed, expected_nodes=3, expected_edges=3, persisted=False)
    assert result['finite_structural_conformance'] is True
    assert result['structural_property_occurrences_audited'] > 10


def test_parallel_edges_and_self_loop_preserved(source):
    _, _, _, bundle = source
    graph = parse(bundle, 'combined_nt')
    snap = next(iter(graph.subjects(RDF.type, _iri('type', 'GraphSnapshot'))))
    edge_ids = set(graph.objects(snap, _iri('property', 'containsEdge')))
    assert len(edge_ids) == 3
    assert len(set(graph.objects(None, _iri('property', 'parallelEdgeOccurrence')))) == 2
    assert any((edge, RDF.subject, graph.value(edge, RDF.object)) in graph for edge in edge_ids)


def test_union_is_exact(source):
    _, _, g5, bundle = source
    assert set(parse(bundle, 'combined_nt')) == set(parse(g5, 'combined_nt')) | set(parse(bundle, 'axioms_nt'))


def test_independent_nt_turtle_parsing(source):
    _, _, _, bundle = source
    for name in ('axioms', 'combined'):
        assert set(parse(bundle, name+'_nt')) == set(Graph().parse(data=bundle[name+'_ttl'].decode(), format='turtle'))


def test_deterministic_build(source):
    view, rdf, g5, bundle = source
    assert build_constraint_layer(view, rdf, g5) == bundle


def test_all_manifest_digests(source):
    bundle = source[-1]
    for name in ('axioms_nt', 'axioms_ttl', 'combined_nt', 'combined_ttl'):
        assert hashlib.sha256(bundle[name]).hexdigest() == bundle['manifest'][name+'_sha256']
    assert hashlib.sha256(canonical({k:v for k,v in bundle['manifest'].items() if k!='manifest_sha256'})).hexdigest() == bundle['manifest']['manifest_sha256']


@pytest.mark.parametrize('field', ['owl_reasoner_consistency_verified', 'owl_entailment_verified',
                                    'scientific_truth_established', 'automatic_approval_permitted',
                                    'authoritative_graph_mutation_permitted'])
def test_authority_flags_false(source, field):
    assert source[-1]['manifest'][field] is False


@pytest.mark.parametrize('member', ['axioms_nt', 'axioms_ttl', 'combined_nt', 'combined_ttl'])
def test_mutated_bytes_rejected_even_if_manifest_rehashed(source, member):
    view, rdf, g5, original = source
    bad = copy.deepcopy(original)
    bad[member] += b'\n'
    bad['manifest'][member+'_sha256'] = hashlib.sha256(bad[member]).hexdigest()
    bad['manifest']['manifest_sha256'] = hashlib.sha256(canonical({k:v for k,v in bad['manifest'].items() if k!='manifest_sha256'})).hexdigest()
    with pytest.raises(OWLConstraintError):
        verify_constraint_layer(view, rdf, g5, bad)


def test_rehashing_false_approval_rejected(source):
    view, rdf, g5, original = source
    bad = copy.deepcopy(original)
    bad['manifest']['automatic_approval_permitted'] = True
    bad['manifest']['manifest_sha256'] = hashlib.sha256(canonical({k:v for k,v in bad['manifest'].items() if k!='manifest_sha256'})).hexdigest()
    with pytest.raises(OWLConstraintError):
        verify_constraint_layer(view, rdf, g5, bad)


def test_changed_source_requires_new_export(source):
    _, _, _, original = source
    changed = make_view()
    changed.graph.nodes[0].attributes['name'] = 'new material'
    rdf = export_view(changed)
    g5 = build_owl_layer(changed, rdf)
    with pytest.raises(OWLConstraintError):
        verify_constraint_layer(changed, rdf, g5, original)


def test_source_bound_to_g5_manifest(source):
    view, rdf, g5, _ = source
    altered = copy.deepcopy(g5)
    altered['manifest']['manifest_sha256'] = '0'*64
    with pytest.raises(OWLConstraintError):
        build_constraint_layer(view, rdf, altered)


@pytest.mark.parametrize('predicate,value', [
    ('nodeIdentifier', Literal('X', datatype=XSD.integer)),
    ('nodeIdentifier', Literal('fr', lang='fr')),
    ('scientificSupportVerified', Literal(True, datatype=XSD.boolean)),
    ('parallelEdgeOccurrence', Literal(-1, datatype=XSD.nonNegativeInteger)),
    ('parallelEdgeOccurrence', Literal('01', datatype=XSD.nonNegativeInteger, normalize=False)),
])
def test_wrong_range_or_authority_rejected(source, predicate, value):
    graph = parse(source[2], 'combined_nt')
    sub,_,old = next(graph.triples((None, _iri('property', predicate), None)))
    graph.remove((sub,_iri('property',predicate),old))
    graph.add((sub,_iri('property',predicate),value))
    with pytest.raises(OWLConstraintError):
        audit_structural_conformance(graph, expected_nodes=3, expected_edges=3, persisted=False)


def test_malformed_domain_rejected(source):
    graph = parse(source[2], 'combined_nt')
    snap = next(graph.subjects(RDF.type,_iri('type','GraphSnapshot')))
    node = next(graph.objects(snap, _iri('property','containsNode')))
    wrong = _iri('node','scientific:child')
    graph.remove((snap, _iri('property','containsNode'), node))
    graph.add((wrong, _iri('property','containsNode'), node))
    with pytest.raises(OWLConstraintError, match='domain'):
        audit_structural_conformance(graph, expected_nodes=3, expected_edges=3, persisted=False)


def test_disconnected_field_rejected(source):
    graph = parse(source[2], 'combined_nt')
    sub,_,old = next(graph.triples((None, _iri('property','entityType'), None)))
    graph.remove((sub, _iri('property','entityType'), old))
    graph.add((_iri('node','new-ghost'), _iri('property','entityType'), old))
    with pytest.raises(OWLConstraintError):
        audit_structural_conformance(graph, expected_nodes=3, expected_edges=3, persisted=False)


def test_undeclared_ontology_inference_prohibited(source):
    graph = parse(source[-1], 'axioms_nt')
    assert not list(graph.triples((None,OWL.imports,None)))
    assert not list(graph.triples((None,OWL.disjointWith,None)))
    assert not list(graph.triples((None,OWL.sameAs,None)))
    assert not list(graph.triples((None,OWL.propertyChainAxiom,None)))


def test_real_persisted_graph(tmp_path):
    store = PersistentDomainGraphStore(ROOT/'.graph-state/scientific')
    state = store.verify()
    view = store.current_view()
    rdf = export_view(view, store_state=state)
    g5 = build_owl_layer(view, rdf, store_state=state)
    bundle = build_constraint_layer(view, rdf, g5, store_state=state)
    assert verify_constraint_layer(view, rdf, g5, bundle, store_state=state) == bundle['manifest']
    assert bundle['manifest']['persisted_store_head'] == state['head']
    assert bundle['manifest']['persisted_store_generation'] == state['generation']


@pytest.mark.parametrize('mode,graph', [('persisted', None), ('candidate', 'examples/graph_engine/ge02_demo_graph.json')])
def test_file_roundtrip_modes(tmp_path, mode, graph):
    p = tmp_path / 'output'
    result = write_constraint_directory(ROOT, p, mode=mode, knowledge_graph=graph)
    assert result == verify_constraint_directory(ROOT, p, mode=mode, knowledge_graph=graph)
    assert read_constraint_directory(p)['manifest'] == result


def test_corrupt_published_ontology_rejected(tmp_path):
    p = tmp_path / 'output'
    write_constraint_directory(ROOT, p, mode='persisted')
    with (p/'owl-constrained-knowledge-graph.nt').open('ab') as fp:
        fp.write(b'\n')
    with pytest.raises(OWLConstraintError):
        verify_constraint_directory(ROOT, p, mode='persisted')


def test_symlinked_published_file_rejected(tmp_path):
    p = tmp_path / 'output'
    write_constraint_directory(ROOT, p, mode='persisted')
    target = p/'owl-structural-axioms.nt'
    target.unlink()
    target.symlink_to(ROOT/'README.md')
    with pytest.raises(Exception):
        verify_constraint_directory(ROOT, p, mode='persisted')


def test_source_repository_cannot_be_output(tmp_path):
    with pytest.raises(Exception):
        write_constraint_directory(ROOT, ROOT/'ontology-danger', mode='persisted')


def test_missing_candidate_rejected(tmp_path):
    with pytest.raises(Exception):
        write_constraint_directory(ROOT, tmp_path/'bad', mode='candidate', knowledge_graph='missing.json')


def test_cli_persisted_end_to_end_with_report(tmp_path):
    output = tmp_path/'ontology'
    env = {**__import__('os').environ, 'PYTHONPATH': str(ROOT)}
    args = [sys.executable, '-m', 'audit_engine.semantic_audit.graph.owl_constraints']
    common = ['--repository',str(ROOT), '--mode','persisted','--output-dir',str(output)]
    first = subprocess.run(args + ['build'] + common, cwd=ROOT, env=env, capture_output=True, text=True)
    assert first.returncode == 0, first.stderr
    report = tmp_path/'verified.json'
    second = subprocess.run(args + ['verify'] + common + ['--report',str(report)], cwd=ROOT, env=env, capture_output=True, text=True)
    assert second.returncode == 0, second.stderr
    obj = json.loads(report.read_bytes())
    assert obj['schema_version'] == REPORT_SCHEMA
    assert obj['finite_structural_conformance'] is True
    assert obj['owl_reasoner_consistency_verified'] is False
    assert obj['report_sha256'] == hashlib.sha256(canonical({k:v for k,v in obj.items() if k!='report_sha256'})).hexdigest()


def test_cli_cannot_reuse_output_directory(tmp_path):
    p = tmp_path/'output'
    write_constraint_directory(ROOT,p,mode='persisted')
    with pytest.raises(Exception):
        write_constraint_directory(ROOT,p,mode='persisted')
