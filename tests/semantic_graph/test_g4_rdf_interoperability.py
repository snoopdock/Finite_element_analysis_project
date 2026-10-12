"""G4.6 source-bound RDF interoperability: real parsing and adversarial negative tests."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest
from rdflib import Graph, Literal, URIRef

from audit_engine.semantic_audit.core.semantic_graph import SemanticEdge, SemanticGraph, SemanticNode
from audit_engine.semantic_audit.graph.domain_integration import GraphDomainView
from audit_engine.semantic_audit.graph.persistent_domain_state import canonical
from audit_engine.semantic_audit.graph.rdf_export import export_view, export_to_directory, read_export, _iri
from audit_engine.semantic_audit.graph.rdf_interoperability import (
    RDFInteroperabilityError, verify_rdf_interoperability, verify_directory,
    _reconstruct, _read_rdf, _write_report, _uri, _property,
)

ROOT = Path(__file__).resolve().parents[2]


def fixture_view():
    graph = SemanticGraph()
    graph.add_node(SemanticNode('a / Δ "', 'ScientificConcept',
                                {'text': 'é\nquote " and backslash \\', 'nested': {'x': [1, True, None]}},
                                {'scientific_truth_established': False}))
    graph.add_node(SemanticNode('b', 'ScientificProposition', {'statement': 'β = δ'}, {}))
    graph.add_edge(SemanticEdge('a / Δ "', 'b', 'HAS_CONCEPT',
                                {'weight': 0.75}, {'source_verified': False}))
    graph.add_edge(SemanticEdge('a / Δ "', 'b', 'HAS_CONCEPT',
                                {'weight': 0.75}, {'source_verified': False}))
    graph.add_edge(SemanticEdge('b', 'b', 'LOOP', {}, {'review': True}))
    return GraphDomainView(graph, 'scientific_knowledge', 'a'*64)


@pytest.fixture
def view():
    return fixture_view()


@pytest.fixture
def bundle(view):
    return export_view(view)


def recalc(bundle):
    temp = copy.deepcopy(bundle)
    m = temp['manifest']
    m['ntriples_sha256'] = hashlib.sha256(temp['ntriples']).hexdigest()
    m['turtle_sha256'] = hashlib.sha256(temp['turtle']).hexdigest()
    m.pop('manifest_sha256', None)
    m['manifest_sha256'] = hashlib.sha256(canonical(m)).hexdigest()
    return temp


def test_parser_round_trip_is_structurally_lossless(view, bundle):
    report = verify_rdf_interoperability(view, bundle)
    assert report['node_count'] == 2
    assert report['edge_occurrence_count'] == 3
    assert report['independent_rdf_parser_equivalence'] is True
    assert report['attributed_multigraph_structure_preserved'] is True
    assert report['report_sha256'] == hashlib.sha256(canonical({k:v for k,v in report.items() if k!='report_sha256'})).hexdigest()


def test_parallel_edges_and_unicode_reconstructed(view, bundle):
    nodes, edges = _reconstruct(_read_rdf(bundle), view)
    assert len(nodes) == 2 and len(edges) == 3
    assert len([e for e in edges if e['relation'] == 'HAS_CONCEPT']) == 2
    assert nodes[0]['attributes'].get('text', nodes[1]['attributes'].get('text')) == 'é\nquote " and backslash \\'
    assert any(e['source'] == e['target'] and e['relation'] == 'LOOP' for e in edges)


def test_source_graph_not_mutated(view, bundle):
    before = copy.deepcopy(view.graph.to_dict())
    verify_rdf_interoperability(view, bundle)
    assert view.graph.to_dict() == before


@pytest.mark.parametrize('key', ['ntriples', 'turtle'])
def test_byte_tamper_detected_even_if_other_serialization_unchanged(view, bundle, key):
    altered = dict(bundle)
    altered[key] += b'\n'
    with pytest.raises(RDFInteroperabilityError):
        verify_rdf_interoperability(view, altered)


def test_modified_manifest_digest_rejected(view, bundle):
    altered = copy.deepcopy(bundle)
    altered['manifest']['node_count'] += 1
    with pytest.raises(RDFInteroperabilityError):
        verify_rdf_interoperability(view, altered)


def test_manifest_authority_forgery_rejected_even_with_valid_hash(view, bundle):
    altered = copy.deepcopy(bundle)
    altered['manifest']['automatic_approval_permitted'] = True
    altered = recalc(altered)
    with pytest.raises(RDFInteroperabilityError, match='authority'):
        verify_rdf_interoperability(view, altered)


def test_rdf_authority_forgery_rejected_with_recalculated_hashes(view, bundle):
    altered = copy.deepcopy(bundle)
    for key in ('ntriples', 'turtle'):
        altered[key] = altered[key].replace(b'"false"^^<http://www.w3.org/2001/XMLSchema#boolean>',
                                           b'"true"^^<http://www.w3.org/2001/XMLSchema#boolean>', 1)
    altered = recalc(altered)
    with pytest.raises(RDFInteroperabilityError):
        verify_rdf_interoperability(view, altered)


def test_unknown_triple_rejected_with_consistent_manifest(view, bundle):
    altered = copy.deepcopy(bundle)
    extraneous = b'<urn:fea:unexpected> <urn:fea:predicate> <urn:fea:object> .\n'
    for key in ('ntriples','turtle'):
        altered[key] += extraneous
    altered['manifest']['triple_count'] += 1
    altered = recalc(altered)
    with pytest.raises(RDFInteroperabilityError, match='Unrecognized'):
        verify_rdf_interoperability(view, altered)


def test_removed_edge_reification_rejected_with_consistent_manifest(view, bundle):
    altered = copy.deepcopy(bundle)
    predicate = _iri('property:containsEdge').encode()
    for key in ('ntriples', 'turtle'):
        lines = altered[key].splitlines(keepends=True)
        matches = [i for i, line in enumerate(lines) if b' '+predicate+b' ' in line]
        assert len(matches) == 3
        lines.pop(matches[0])
        altered[key] = b''.join(lines)
    altered['manifest']['triple_count'] -= 1
    altered = recalc(altered)
    with pytest.raises(RDFInteroperabilityError):
        verify_rdf_interoperability(view, altered)


def test_duplicate_statement_occurrence_rejected(view, bundle):
    graph = _read_rdf(bundle)
    edge_subjects = list(graph.objects(_uri('snapshot', view.fingerprint), _property('containsEdge')))
    assert len(edge_subjects) == 3
    # Rewriting occurrence on one statement makes it inconsistent with resource digest.
    subject = edge_subjects[0]
    pred = _property('parallelEdgeOccurrence')
    old = next(graph.objects(subject, pred))
    graph.remove((subject, pred, old))
    graph.add((subject, pred, Literal(900, datatype=old.datatype)))
    with pytest.raises(RDFInteroperabilityError):
        _reconstruct(graph, view)


def test_invalid_node_type_rejected(view, bundle):
    graph = _read_rdf(bundle)
    graphiri = _uri('snapshot', view.fingerprint)
    node = next(graph.objects(graphiri, _property('containsNode')))
    graph.remove((node, URIRef('http://www.w3.org/1999/02/22-rdf-syntax-ns#type'), None))
    with pytest.raises(RDFInteroperabilityError):
        _reconstruct(graph, view)


def test_source_snapshot_mismatch_even_with_self_consistent_rdf(bundle):
    unrelated = fixture_view()
    unrelated.graph.nodes[0].attributes['new'] = True
    with pytest.raises(RDFInteroperabilityError):
        verify_rdf_interoperability(unrelated, bundle)


def test_false_scientific_claims_remain_false(view, bundle):
    report = verify_rdf_interoperability(view, bundle)
    for field in ('semantic_entailment_verified', 'scientific_truth_established',
                  'automatic_approval_permitted', 'authoritative_graph_mutation_permitted'):
        assert report[field] is False


def test_ge02_persisted_store_real_end_to_end(tmp_path):
    output = tmp_path/'rdf'
    before = (ROOT/'.graph-state/scientific/HEAD.json').read_bytes()
    export_to_directory(ROOT, output, mode='persisted')
    report = verify_directory(ROOT, output)
    assert report['persisted_store_generation'] >= 1
    assert report['node_count'] == 3
    assert report['edge_occurrence_count'] == 2
    assert (ROOT/'.graph-state/scientific/HEAD.json').read_bytes() == before


def test_candidate_graph_end_to_end(tmp_path):
    output = tmp_path/'rdf'
    export_to_directory(ROOT, output, mode='candidate', knowledge_graph='examples/graph_engine/ge02_demo_graph.json')
    report = verify_directory(ROOT, output, mode='candidate',
                              knowledge_graph='examples/graph_engine/ge02_demo_graph.json')
    assert report['persisted_store_head'] is None
    assert report['node_count'] == 3


def test_unrecognized_candidate_path_rejected(tmp_path):
    output = tmp_path/'rdf'
    export_to_directory(ROOT, output, mode='persisted')
    with pytest.raises((ValueError, RDFInteroperabilityError)):
        verify_directory(ROOT, output, mode='candidate', knowledge_graph='../outside.json')


def test_nonexistent_export_directory_rejected(tmp_path):
    with pytest.raises((OSError, ValueError)):
        verify_directory(ROOT, tmp_path/'no-rdf')


def test_symlinked_rdf_bundle_member_rejected(tmp_path):
    export_to_directory(ROOT, tmp_path/'rdf', mode='persisted')
    f = tmp_path/'rdf/semantic-graph.nt'
    copy_path = tmp_path/'real.nt'
    f.rename(copy_path)
    f.symlink_to(copy_path)
    with pytest.raises((OSError, ValueError)):
        verify_directory(ROOT, tmp_path/'rdf')


def test_report_written_only_outside_repositories(tmp_path, view, bundle):
    report = verify_rdf_interoperability(view, bundle)
    path = tmp_path/'report.json'
    _write_report(path, ROOT, report)
    assert json.loads(path.read_text()) == report
    with pytest.raises(RDFInteroperabilityError):
        _write_report(path, ROOT, report)
    with pytest.raises(RDFInteroperabilityError):
        _write_report(ROOT/'G4.6-unauthorized.json', ROOT, report)


def test_report_symlink_parent_rejected(tmp_path, view, bundle):
    report = verify_rdf_interoperability(view, bundle)
    real = tmp_path/'real'
    real.mkdir()
    link = tmp_path/'link'
    link.symlink_to(real, target_is_directory=True)
    with pytest.raises(RDFInteroperabilityError):
        _write_report(link/'report.json', ROOT, report)


def test_cli_persisted_produces_auditable_report(tmp_path):
    export_to_directory(ROOT, tmp_path/'rdf', mode='persisted')
    command = [sys.executable, '-m', 'audit_engine.semantic_audit.graph.rdf_interoperability',
               '--repository', str(ROOT), '--export-dir', str(tmp_path/'rdf'),
               '--mode', 'persisted', '--report', str(tmp_path/'report.json')]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == json.loads((tmp_path/'report.json').read_text())


def test_cli_rejects_tampered_bundle_without_report(tmp_path):
    export_to_directory(ROOT, tmp_path/'rdf', mode='persisted')
    with (tmp_path/'rdf/semantic-graph.nt').open('ab') as f:
        f.write(b'\n')
    command = [sys.executable, '-m', 'audit_engine.semantic_audit.graph.rdf_interoperability',
               '--repository', str(ROOT), '--export-dir', str(tmp_path/'rdf'),
               '--report', str(tmp_path/'report.json')]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=20)
    assert result.returncode == 2
    assert not (tmp_path/'report.json').exists()


def test_cli_rejects_missing_persisted_head(tmp_path):
    repo = tmp_path/'emptyrepo'
    repo.mkdir()
    with pytest.raises((OSError, ValueError)):
        verify_directory(repo, tmp_path/'rdf')


def test_standard_parser_rejects_unparseable_rdf(view, bundle):
    altered = copy.deepcopy(bundle)
    altered['turtle'] = b'@prefix x: <urn:bad> . <broken'
    altered = recalc(altered)
    with pytest.raises(RDFInteroperabilityError):
        verify_rdf_interoperability(view, altered)
