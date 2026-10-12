"""G5.1 executable ontology tests for actual GE/G4 contracts and unsafe inputs."""
import copy
import hashlib
from pathlib import Path
import subprocess
import sys

import pytest
from rdflib import Graph, URIRef
from rdflib.namespace import RDF, RDFS, OWL, XSD

from audit_engine.semantic_audit.core.semantic_graph import SemanticNode, SemanticEdge, SemanticGraph
from audit_engine.semantic_audit.graph.domain_integration import GraphDomainView
from audit_engine.semantic_audit.graph.persistent_domain_state import PersistentDomainGraphStore, canonical
from audit_engine.semantic_audit.graph.rdf_export import export_view
from audit_engine.semantic_audit.graph.owl_ontology import (
    OWLOntologyError, ONTOLOGY, _iri, _prop, build_owl_layer,
    verify_owl_layer, write_owl_directory, read_owl_directory,
    verify_owl_directory,
)

ROOT = Path(__file__).resolve().parents[2]


def source_view():
    graph = SemanticGraph()
    graph.add_node(SemanticNode('scientific:1 / α', 'ScientificConcept', {'name': 'Finite-element Δ'}, {}))
    graph.add_node(SemanticNode('scientific:2', 'ScientificProposition', {'statement': 'u = f(x)'}, {}))
    graph.add_node(SemanticNode('scientific:source:xyz', 'ScientificSourceRef', {}, {}))
    graph.add_edge(SemanticEdge('scientific:1 / α', 'scientific:2', 'HAS_CONCEPT', {'v': 1}, {}))
    graph.add_edge(SemanticEdge('scientific:1 / α', 'scientific:2', 'HAS_CONCEPT', {'v': 1}, {}))
    graph.add_edge(SemanticEdge('scientific:2', 'scientific:2', 'SELF_LINK', {}, {}))
    return GraphDomainView(graph, 'scientific_knowledge', 'a'*64)


@pytest.fixture
def view():
    return source_view()


@pytest.fixture
def rdf_bundle(view):
    return export_view(view)


@pytest.fixture
def bundle(view, rdf_bundle):
    return build_owl_layer(view, rdf_bundle)


def test_ontology_is_declared(bundle):
    graph = Graph().parse(data=bundle['ontology_nt'].decode(), format='nt')
    assert (ONTOLOGY, RDF.type, OWL.Ontology) in graph
    assert (ONTOLOGY, _prop('owlEntailmentVerified'), None) in graph
    assert not list(graph.objects(ONTOLOGY, OWL.imports))


@pytest.mark.parametrize('typ', ['ScientificConcept', 'ScientificProposition', 'ScientificSourceRef'])
def test_node_classes_are_structural_subclasses(bundle, typ):
    graph = Graph().parse(data=bundle['ontology_nt'].decode(), format='nt')
    assert (_iri('type', typ), RDF.type, OWL.Class) in graph
    assert (_iri('type', typ), RDFS.subClassOf, _iri('type', 'SemanticEntity')) in graph


@pytest.mark.parametrize('relation', ['HAS_CONCEPT', 'SELF_LINK'])
def test_relation_properties_are_declared_as_object_properties(bundle, relation):
    graph = Graph().parse(data=bundle['ontology_nt'].decode(), format='nt')
    assert (_iri('relation', relation), RDF.type, OWL.ObjectProperty) in graph


@pytest.mark.parametrize('name', ['containsNode', 'containsEdge'])
def test_graph_membership_is_an_object_property(bundle, name):
    graph = Graph().parse(data=bundle['ontology_nt'].decode(), format='nt')
    assert (_iri('property', name), RDF.type, OWL.ObjectProperty) in graph


@pytest.mark.parametrize('name', ['attributesJson', 'nodeIdentifier', 'parallelEdgeOccurrence',
                                  'scientificTruthEstablished', 'sourceNotInSchema'])
def test_datatype_properties_have_explicit_contract(bundle, name):
    graph = Graph().parse(data=bundle['ontology_nt'].decode(), format='nt')
    if name == 'sourceNotInSchema':
        assert (_iri('property', name), RDF.type, OWL.DatatypeProperty) not in graph
    else:
        assert (_iri('property', name), RDF.type, OWL.DatatypeProperty) in graph


def test_structural_union_is_exact_source_plus_ontology(view, rdf_bundle, bundle):
    source = Graph().parse(data=rdf_bundle['ntriples'].decode(), format='nt')
    schema = Graph().parse(data=bundle['ontology_nt'].decode(), format='nt')
    combined = Graph().parse(data=bundle['combined_nt'].decode(), format='nt')
    assert set(combined) == set(source) | set(schema)
    assert len([x for x in combined.triples((None, _iri('property', 'containsEdge'), None))]) == 3
    assert verify_owl_layer(view, rdf_bundle, bundle) == bundle['manifest']


def test_both_serializations_parse_identically(bundle):
    for name in ('ontology', 'combined'):
        nt = Graph().parse(data=bundle[name+'_nt'].decode(), format='nt')
        ttl = Graph().parse(data=bundle[name+'_ttl'].decode(), format='turtle')
        assert set(nt) == set(ttl)


def test_metadata_is_source_bound(view, rdf_bundle, bundle):
    graph = Graph().parse(data=bundle['ontology_nt'].decode(), format='nt')
    assert str(graph.value(ONTOLOGY, _prop('sourceGraphFingerprint'))) == view.fingerprint
    assert str(graph.value(ONTOLOGY, _prop('rdfExportManifestSha256'))) == rdf_bundle['manifest']['manifest_sha256']


def test_no_unapproved_inference_vocabulary(bundle):
    graph = Graph().parse(data=bundle['combined_nt'].decode(), format='nt')
    assert not any(p in {OWL.imports, OWL.sameAs, OWL.equivalentClass, OWL.inverseOf,
                         OWL.propertyChainAxiom, OWL.disjointWith, OWL.hasKey}
                   for _, p, _ in graph)


def test_no_reasoner_or_approval_assertion(bundle):
    manifest = bundle['manifest']
    for name in ('owl_entailment_verified', 'scientific_truth_established',
                 'automatic_approval_permitted', 'authoritative_graph_mutation_permitted'):
        assert manifest[name] is False


def test_same_input_deterministic(view, rdf_bundle, bundle):
    assert build_owl_layer(view, rdf_bundle) == bundle


def test_reverse_order_preserves_ontology_fingerprint(view, rdf_bundle, bundle):
    inverted = GraphDomainView(SemanticGraph(), view.domain, view.input_sha256)
    for node in reversed(view.graph.nodes):
        inverted.graph.add_node(copy.deepcopy(node))
    for edge in reversed(view.graph.edges):
        inverted.graph.add_edge(copy.deepcopy(edge))
    assert build_owl_layer(inverted, export_view(inverted)) == bundle


def test_read_only(view, rdf_bundle):
    before = copy.deepcopy(view.graph.to_dict())
    build_owl_layer(view, rdf_bundle)
    assert view.graph.to_dict() == before


@pytest.mark.parametrize('member', ['ontology_nt', 'ontology_ttl', 'combined_nt', 'combined_ttl'])
def test_mutated_bytes_are_rejected_even_with_rehashed_manifest(view, rdf_bundle, bundle, member):
    altered = copy.deepcopy(bundle)
    altered[member] += b'\n<urn:invalid:x> <urn:invalid:y> <urn:invalid:z> .\n'
    altered['manifest'][member+'_sha256'] = hashlib.sha256(altered[member]).hexdigest()
    altered['manifest'].pop('manifest_sha256')
    altered['manifest']['manifest_sha256'] = hashlib.sha256(canonical(altered['manifest'])).hexdigest()
    with pytest.raises(OWLOntologyError):
        verify_owl_layer(view, rdf_bundle, altered)


@pytest.mark.parametrize('field', ['owl_entailment_verified', 'scientific_truth_established',
                                   'automatic_approval_permitted', 'authoritative_graph_mutation_permitted'])
def test_forged_permissions_rejected(view, rdf_bundle, bundle, field):
    altered = copy.deepcopy(bundle)
    altered['manifest'][field] = True
    altered['manifest'].pop('manifest_sha256')
    altered['manifest']['manifest_sha256'] = hashlib.sha256(canonical(altered['manifest'])).hexdigest()
    with pytest.raises(OWLOntologyError):
        verify_owl_layer(view, rdf_bundle, altered)


def test_source_rdf_modification_rejected(view, rdf_bundle):
    forged = copy.deepcopy(rdf_bundle)
    forged['ntriples'] += b'\n'
    with pytest.raises(OWLOntologyError):
        build_owl_layer(view, forged)


def test_changed_source_requires_new_ontology(view, rdf_bundle, bundle):
    changed = source_view()
    changed.graph.nodes[0].attributes['name'] = 'Changed assumption'
    with pytest.raises(OWLOntologyError):
        verify_owl_layer(changed, export_view(changed), bundle)


def test_unverified_evidence_does_not_gain_authority(view, rdf_bundle, bundle):
    schema = Graph().parse(data=bundle['ontology_nt'].decode(), format='nt')
    assert (ONTOLOGY, _prop('scientificTruthEstablished'), None) in schema
    assert str(schema.value(ONTOLOGY, _prop('scientificTruthEstablished'))) == 'false'


def test_persisted_real_state(tmp_path):
    store = PersistentDomainGraphStore(ROOT/'.graph-state/scientific')
    state = store.verify()
    view = store.current_view()
    bundle = build_owl_layer(view, export_view(view, store_state=state), store_state=state)
    assert bundle['manifest']['persisted_store_head'] == state['head']
    assert bundle['manifest']['persisted_store_generation'] == state['generation']
    assert bundle['manifest']['g4_triple_count'] == export_view(view, store_state=state)['manifest']['triple_count']
    assert bundle['manifest']['g4_triple_count'] > 0


def test_file_round_trip_candidate(tmp_path):
    output = tmp_path/'output'
    manifest = write_owl_directory(ROOT, output, mode='candidate',
                                   knowledge_graph='examples/graph_engine/ge02_demo_graph.json')
    assert manifest == verify_owl_directory(ROOT, output, mode='candidate',
                                            knowledge_graph='examples/graph_engine/ge02_demo_graph.json')
    assert read_owl_directory(output)['manifest'] == manifest


def test_file_round_trip_persisted(tmp_path):
    output = tmp_path/'output'
    manifest = write_owl_directory(ROOT, output, mode='persisted')
    assert manifest == verify_owl_directory(ROOT, output, mode='persisted')


def test_reject_source_output(tmp_path):
    from audit_engine.semantic_audit.graph.rdf_export import RDFExportError
    with pytest.raises(RDFExportError):
        write_owl_directory(ROOT, ROOT/'forbidden-g5-output', mode='persisted')


def test_traversal_candidate_rejected(tmp_path):
    with pytest.raises((OWLOntologyError, ValueError)):
        write_owl_directory(ROOT, tmp_path/'bad', mode='candidate', knowledge_graph='../elsewhere.json')


def test_missing_candidate_rejected(tmp_path):
    with pytest.raises((OWLOntologyError, ValueError)):
        write_owl_directory(ROOT, tmp_path/'bad', mode='candidate', knowledge_graph='does-not-exist.json')


def test_existing_output_rejected(tmp_path):
    folder = tmp_path/'already'
    folder.mkdir()
    from audit_engine.semantic_audit.graph.rdf_export import RDFExportError
    with pytest.raises(RDFExportError):
        write_owl_directory(ROOT, folder, mode='persisted')


def test_symlinked_artifact_rejected(tmp_path):
    a = tmp_path/'a'
    write_owl_directory(ROOT, a, mode='persisted')
    (a/'ontology-schema.nt').unlink()
    (a/'ontology-schema.nt').symlink_to(ROOT/'README.md')
    from audit_engine.semantic_audit.graph.rdf_export import RDFExportError
    with pytest.raises(RDFExportError):
        verify_owl_directory(ROOT, a, mode='persisted')


def test_candidate_cli_end_to_end(tmp_path):
    out = tmp_path/'out'
    env = {**__import__('os').environ, 'PYTHONPATH': str(ROOT)}
    cmd = [sys.executable, '-m', 'audit_engine.semantic_audit.graph.owl_ontology']
    common = ['--repository', str(ROOT), '--mode', 'candidate',
              '--knowledge-graph', 'examples/graph_engine/ge02_demo_graph.json',
              '--output-dir', str(out)]
    build = subprocess.run(cmd + ['build'] + common, env=env, capture_output=True, text=True)
    assert build.returncode == 0, build.stderr
    verify = subprocess.run(cmd + ['verify'] + common + ['--report', str(tmp_path/'report.json')],
                            env=env, capture_output=True, text=True)
    assert verify.returncode == 0, verify.stderr
    report = __import__('json').loads((tmp_path/'report.json').read_text())
    assert report['source_bound_owl_parsing_verified'] is True
    assert report['owl_entailment_verified'] is False
    assert report['report_sha256'] == hashlib.sha256(canonical({k:v for k,v in report.items() if k != 'report_sha256'})).hexdigest()
