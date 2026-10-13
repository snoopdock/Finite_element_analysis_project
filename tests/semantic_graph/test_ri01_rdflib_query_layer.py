"""RI-01: source-bound RDFLib query and named-graph regression tests."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import types

import pytest
from rdflib import Dataset, Graph, Literal, URIRef
from rdflib.namespace import RDF, XSD

from audit_engine.semantic_audit.core.semantic_graph import SemanticGraph, SemanticNode, SemanticEdge
from audit_engine.semantic_audit.graph.domain_integration import GraphDomainView
from audit_engine.semantic_audit.graph.persistent_domain_state import canonical
from audit_engine.semantic_audit.graph import rdflib_query_layer as mod


@pytest.fixture
def view():
    graph = SemanticGraph()
    graph.add_node(SemanticNode('fem:a', 'ScientificConcept',
                                {'name': 'Constitutive law', 'status': 'proposed',
                                 'nested': {'this': ['stays', 'json']}}, {}))
    graph.add_node(SemanticNode('fem:b', 'ScientificProposition',
                                {'statement': 'sigma = E * epsilon', 'status': 'draft'}, {}))
    graph.add_edge(SemanticEdge('fem:a', 'fem:b', 'HAS_CONCEPT',
                                {'weight': 0.8}, {'source_verified': False}))
    graph.add_edge(SemanticEdge('fem:a', 'fem:b', 'HAS_CONCEPT',
                                {'weight': 0.8}, {'source_verified': False}))
    graph.add_edge(SemanticEdge('fem:b', 'fem:b', 'SELF', {}, {}))
    return GraphDomainView(graph, 'scientific_knowledge', 'c' * 64)


@pytest.fixture
def fixture_g4(monkeypatch):
    """Stand-in G4 projection isolates RDFLib SPARQL tests from the older local ZIP.

    The real G4.5/4.6 integration is tested separately on the current GitHub
    development branch; this fixture does not establish G4 integrity itself.
    """
    source = 'audit_engine.semantic_audit.graph.'
    fake = types.ModuleType(source + 'rdf_export')
    fake.NS = 'urn:fea:semantic-graph:v1:'

    def uri(kind, value):
        from urllib.parse import quote
        return URIRef(fake.NS + quote(f'{kind}:{value}', safe=''))

    def emit(view, *, store_state=None):
        g = Graph()
        snap = uri('snapshot', view.fingerprint)
        g.add((snap, uri('property', 'domain'), Literal(view.domain)))
        for node in view.graph.nodes:
            n = uri('node', node.node_id)
            g.add((snap, uri('property', 'containsNode'), n))
            g.add((n, uri('property', 'nodeIdentifier'), Literal(node.node_id)))
            g.add((n, uri('property', 'entityType'), Literal(node.entity_type)))
        occurrences = {}
        for edge in view.graph.edges:
            key = (edge.source_id, edge.target_id, edge.relation_type)
            occur = occurrences.get(key, 0)
            occurrences[key] = occur + 1
            r = uri('edge', f'{key}:{occur}')
            g.add((snap, uri('property', 'containsEdge'), r))
            g.add((r, RDF.subject, uri('node', edge.source_id)))
            g.add((r, RDF.object, uri('node', edge.target_id)))
            g.add((r, uri('property', 'relationType'), Literal(edge.relation_type)))
            g.add((r, uri('property', 'parallelEdgeOccurrence'), Literal(occur, datatype=XSD.nonNegativeInteger)))
        raw = g.serialize(format='nt').encode('utf-8')
        return {'ntriples': raw,
                'manifest': {'manifest_sha256': hashlib.sha256(raw).hexdigest()}}

    fake.export_view = emit
    fake_interop = types.ModuleType(source + 'rdf_interoperability')
    fake_interop._read_rdf = lambda bundle: Graph().parse(data=bundle['ntriples'], format='nt')
    fake_interop.verify_rdf_interoperability = lambda v,b,store_state=None: {
        'triple_count': len(fake_interop._read_rdf(b)),
    }
    monkeypatch.setitem(sys.modules, source + 'rdf_export', fake)
    monkeypatch.setitem(sys.modules, source + 'rdf_interoperability', fake_interop)
    return fake, fake_interop


@pytest.fixture
def derived(view, fixture_g4):
    return mod.build_verified_dataset(view)


def test_real_graph_fingerprint_stable(view):
    assert view.fingerprint == view.fingerprint
    assert len(view.graph.edges) == 3


def test_three_named_contexts_and_source_triples(derived):
    assert len({derived.asserted_context, derived.fields_context, derived.provenance_context}) == 3
    assert len(derived.dataset.graph(derived.asserted_context)) > 0
    assert len(derived.dataset.graph(derived.fields_context)) == 4
    assert len(derived.dataset.graph(derived.provenance_context)) > 0


def test_literal_metadata_projection_is_selective(derived):
    predicates = {str(p) for _,p,_ in derived.dataset.graph(derived.fields_context)}
    assert str(mod._field_iri('name')) in predicates
    assert 'nested' not in ''.join(predicates)
    with pytest.raises(mod.RDFQueryLayerError):
        mod._field_iri('nested')


def test_query_nodes_by_type(derived):
    r = derived.query('nodes_by_type', 'ScientificConcept')
    assert len(r) == 1
    assert r[0]['nodeId']['value'] == 'fem:a'
    assert r[0]['node']['type'] == 'iri'


def test_query_nonmatching_type_is_empty(derived):
    assert derived.query('nodes_by_type', 'NotAType') == []


def test_edge_occurrence_query_does_not_collapse_parallel_edges(derived):
    r = derived.query('edge_occurrences_by_relation', 'HAS_CONCEPT')
    assert len(r) == 2
    assert {int(e['occurrence']['value']) for e in r} == {0,1}
    assert r[0]['statement']['value'] != r[1]['statement']['value']


def test_self_loop_retained(derived):
    results = derived.query('edge_occurrences_by_relation', 'SELF')
    assert len(results) == 1
    assert results[0]['source']['value'] == results[0]['target']['value']


@pytest.mark.parametrize('field,value', [
    ('name', 'Constitutive law'),
    ('statement', 'sigma = E * epsilon'),
    ('status', 'draft'),
])
def test_query_typed_field(derived, field, value):
    results = derived.query('nodes_by_field', field)
    assert any(x['value']['value'] == value for x in results)


@pytest.mark.parametrize('query,arg,limit', [
    ('DELETE WHERE { ?s ?p ?o }', 'x', 5),
    ('SERVICE <https://example.org>', 'x', 5),
    ('arbitrary', 'x', 5),
    ('nodes_by_field', 'metadataJson', 5),
    ('nodes_by_type', 'ScientificConcept', 0),
    ('nodes_by_type', 'ScientificConcept', 201),
    ('nodes_by_type', 'ScientificConcept', True),
    ('nodes_by_type', '', 5),
])
def test_catalog_rejects_unsafe_or_unbounded_queries(derived, query,arg,limit):
    with pytest.raises(mod.RDFQueryLayerError):
        derived.query(query, arg, limit)


def test_sparql_parameter_is_not_interpolated(derived):
    injection = "ScientificConcept' } UNION { ?s ?p ?o } #"
    assert derived.query('nodes_by_type', injection) == []


def test_nquads_are_deterministic(derived):
    x = mod._nq(derived.dataset, (derived.asserted_context,
                                 derived.fields_context, derived.provenance_context))
    assert x == derived.nquads
    assert x.endswith(b' .\n')
    assert x == b''.join(sorted(x.splitlines(keepends=True)))


def test_nquads_rdf_dataset_parses_with_exact_quads(derived):
    ds = Dataset()
    ds.parse(data=derived.nquads.decode(), format='nquads')
    assert set(ds.quads((None,None,None,None))) == set(derived.dataset.quads((None,None,None,None)))


def test_provenance_false_authority_flags(derived):
    g = derived.dataset.graph(derived.provenance_context)
    for name in ('scientific_truth_established', 'semantic_entailment_verified',
                 'automatic_approval_permitted', 'authoritative_mutation_permitted'):
        assert list(g.objects(None, mod._uri('query-provenance', name))) == [Literal(False, datatype=XSD.boolean)]


def test_report_is_replayable_and_integrity_bound(view, fixture_g4, tmp_path, monkeypatch):
    monkeypatch.setattr(mod,'resolve_view',lambda *a, **kw:(view,None))
    a, nq = mod.build_report(tmp_path, mode='candidate',knowledge_graph='a.json',
                             query_id='edge_occurrences_by_relation',argument='HAS_CONCEPT',limit=10)
    b, bnq = mod.build_report(tmp_path, mode='candidate',knowledge_graph='a.json',
                             query_id='edge_occurrences_by_relation',argument='HAS_CONCEPT',limit=10)
    assert a == b and nq == bnq
    assert a['result_count'] == 2 and a['parallel_edge_occurrences_preserved'] is True
    assert a['report_sha256'] == hashlib.sha256(canonical({k:v for k,v in a.items() if k!='report_sha256'})).hexdigest()
    repo = tmp_path / 'source'; repo.mkdir()
    out = tmp_path/'new-detached'
    mod.write_report(out,repo,a,nq)
    assert mod.verify_report(out,repo,mode='candidate',knowledge_graph='a.json',
                             query_id='edge_occurrences_by_relation',argument='HAS_CONCEPT',limit=10) == a
    (out/'rdf-query-report.json').write_text('{}')
    with pytest.raises(mod.RDFQueryLayerError):
        mod.verify_report(out,repo,mode='candidate',knowledge_graph='a.json',
                          query_id='edge_occurrences_by_relation',argument='HAS_CONCEPT',limit=10)


def test_report_rejects_nquads_tampering(view, fixture_g4, tmp_path, monkeypatch):
    monkeypatch.setattr(mod,'resolve_view',lambda *a, **kw:(view,None))
    a, nq = mod.build_report(tmp_path, mode='candidate',knowledge_graph='a.json',
                             query_id='nodes_by_field',argument='status',limit=10)
    repo=tmp_path/'source'; repo.mkdir()
    out=tmp_path/'detached';mod.write_report(out,repo,a,nq)
    (out/'rdf-dataset.nq').write_bytes(nq+b'\n')
    with pytest.raises(mod.RDFQueryLayerError):
        mod.verify_report(out,repo,mode='candidate',knowledge_graph='a.json',
                          query_id='nodes_by_field',argument='status',limit=10)


def test_source_unchanged(view,fixture_g4):
    before=copy.deepcopy(view.graph.to_dict())
    mod.build_verified_dataset(view).query('nodes_by_type','ScientificConcept')
    assert before == view.graph.to_dict()


def test_missing_source_proof_fails_closed(view,fixture_g4,monkeypatch):
    _, interop=fixture_g4
    def reject(*a,**k):raise ValueError('proof failed')
    monkeypatch.setattr(interop,'verify_rdf_interoperability',reject)
    with pytest.raises(ValueError,match='proof failed'):
        mod.build_verified_dataset(view)


def test_bad_provenance_state_rejected_by_native_exporter(view,fixture_g4,monkeypatch):
    exporter,_=fixture_g4
    def reject_if_state(view,*,store_state=None):
        if store_state is not None:raise ValueError('bad provenance')
        return fixture_g4[0].export_view(view)
    monkeypatch.setattr(exporter,'export_view',reject_if_state)
    with pytest.raises(ValueError, match='bad provenance'):
        mod.build_verified_dataset(view,store_state={'status':'forged'})


def test_no_blank_nodes_in_nquads(derived):
    from rdflib import BNode
    derived.dataset.graph(derived.fields_context).add((BNode(),mod._field_iri('name'),Literal('hi')))
    with pytest.raises(mod.RDFQueryLayerError,match='Blank'):
        mod._nq(derived.dataset,(derived.fields_context,))


def test_output_must_not_be_inside_repository(tmp_path):
    (tmp_path/'stage').mkdir()
    with pytest.raises(mod.RDFQueryLayerError):
        mod._safe_output(tmp_path/'stage'/'report',tmp_path/'stage')


def test_existing_output_must_not_be_replaced(tmp_path):
    (tmp_path/'existing').mkdir()
    with pytest.raises(mod.RDFQueryLayerError):
        mod._safe_output(tmp_path/'existing',tmp_path)


def test_invalid_scalar_types_skipped():
    assert mod._literal({'struct':'not a scalar'}) is None
    assert mod._literal(float('nan')) is None
    assert mod._literal(None) is None
    assert mod._literal(True).datatype == XSD.boolean
    assert mod._literal(10).datatype == XSD.integer


def test_real_persisted_rdf_export_end_to_end():
    # This requires the G4.5 file present on the current development branch.
    pytest.importorskip('audit_engine.semantic_audit.graph.rdf_export')
    root=Path(__file__).resolve().parents[2]
    state,st=mod.resolve_view(root,mode='persisted')
    result=mod.build_verified_dataset(state,store_state=st)
    assert result.query('nodes_by_type','ScientificConcept')
    assert result.g4_manifest['schema_version']=='g4-rdf-export/v1'


def test_real_candidate_rdf_export_end_to_end():
    pytest.importorskip('audit_engine.semantic_audit.graph.rdf_export')
    root=Path(__file__).resolve().parents[2]
    state,st=mod.resolve_view(root,mode='candidate',knowledge_graph='examples/graph_engine/ge02_demo_graph.json')
    result=mod.build_verified_dataset(state,store_state=st)
    assert result.query('nodes_by_field','name')
