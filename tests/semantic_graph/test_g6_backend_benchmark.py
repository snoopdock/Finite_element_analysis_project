"""G6.1 scientific graph benchmark: parity, provenance and adversarial guards."""
from pathlib import Path

import pytest

from audit_engine.semantic_audit.core.semantic_graph import SemanticEdge, SemanticGraph, SemanticNode
from audit_engine.semantic_audit.graph.backend.networkx_adapter import NetworkXAdapter
from audit_engine.semantic_audit.graph.backend.scipy_adapter import SciPyAdapter
from audit_engine.semantic_audit.graph.backend import backend_benchmark as bb


@pytest.fixture(scope='module')
def miniature():
    return bb.generate_graph(16, 60, seed=1999)


def test_synthetic_identical_same_seed():
    assert bb.generate_graph(40, 230, 111).to_dict() == bb.generate_graph(40, 230, 111).to_dict()


def test_synthetic_different_seeds():
    assert bb.generate_graph(40, 230, 111).to_dict() != bb.generate_graph(40, 230, 112).to_dict()


def test_synthetic_parallel_and_self_loops():
    g = bb.generate_graph(16, 400, 57)
    data = bb.verify_projection(g, NetworkXAdapter(g), SciPyAdapter(g))
    assert data['unique_pairs'] < data['multiedge_occurrences']
    assert data['self_loops'] > 0


def test_nx_preserves_node_and_edge_metadata(miniature):
    a = NetworkXAdapter(miniature)
    assert bb.verify_projection(miniature, a, SciPyAdapter(miniature))['status'] == 'verified'
    assert all(a.export().nodes[n.node_id]['metadata'] == n.metadata for n in miniature.nodes)


def test_scipy_edge_count_and_sidechannels(miniature):
    a = SciPyAdapter(miniature)
    assert a.export().sum() == len(miniature.edges)
    assert len(a.metadata['edges']) == len(miniature.edges)
    assert a.capabilities()['lossless'] is False


def test_scipy_directionality():
    g = SemanticGraph(nodes=[SemanticNode('a','X'), SemanticNode('b','Y')],
                      edges=[SemanticEdge('a','b','REF')])
    a = SciPyAdapter(g)
    assert bb._sp_reach(a,'a') == {'a','b'}
    assert bb._sp_reach(a,'b') == {'b'}


def test_scipy_selfloop():
    g = SemanticGraph(nodes=[SemanticNode('a','X')],
                      edges=[SemanticEdge('a','a','REF')])
    assert bb.verify_projection(g, NetworkXAdapter(g), SciPyAdapter(g))['self_loops'] == 1


def test_graph_disconnected():
    g = bb.generate_graph(16, 0, 2)
    assert all(q['reachable'] == 1 for q in bb.verify_projection(g, NetworkXAdapter(g), SciPyAdapter(g))['queries'])


def test_graph_nontrivial_reachability():
    g = bb.generate_graph(16, 55, 4)
    assert bb.verify_projection(g, NetworkXAdapter(g), SciPyAdapter(g))['queries'][0]['reachable'] == 16


def test_corrupted_nx_edge_projection(miniature):
    a = NetworkXAdapter(miniature)
    a.export().remove_edge(miniature.edges[0].source_id, miniature.edges[0].target_id)
    with pytest.raises(bb.BenchmarkError, match='multiedge'):
        bb.verify_projection(miniature, a, SciPyAdapter(miniature))


def test_corrupted_scipy_matrix(miniature):
    a = SciPyAdapter(miniature)
    a.matrix = a.matrix * 2
    with pytest.raises(bb.BenchmarkError, match='multiplicity|total'):
        bb.verify_projection(miniature, NetworkXAdapter(miniature), a)


def test_corrupted_nx_metadata(miniature):
    a = NetworkXAdapter(miniature)
    a.export().nodes[miniature.nodes[0].node_id]['entity_type'] = 'Forged'
    with pytest.raises(bb.BenchmarkError, match='payload'):
        bb.verify_projection(miniature, a, SciPyAdapter(miniature))


def test_corrupted_scipy_identity(miniature):
    a = SciPyAdapter(miniature)
    a.index_to_node[0] = 'wrong'
    with pytest.raises(bb.BenchmarkError, match='mapping'):
        bb.verify_projection(miniature, NetworkXAdapter(miniature), a)


def test_bad_dimensions():
    for n,e in ((0,0),(10001,0),(3,-1),(3,100001)):
        with pytest.raises(bb.BenchmarkError):
            bb.generate_graph(n,e,5)


def test_duplicate_graph_id_rejected():
    g = SemanticGraph(nodes=[SemanticNode('x','X'),SemanticNode('x','X')])
    with pytest.raises(bb.BenchmarkError, match='Duplicate'):
        bb.verify_projection(g, NetworkXAdapter(g), SciPyAdapter(g))


def test_benchmark_metrics_shape(miniature):
    out = bb.benchmark_graph(miniature,repeats=3,warmup=0)
    assert out['nodes'] == 16
    assert out['edge_occurrences'] == 60
    assert set(out['timings']) == {'networkx','scipy'}
    for row in out['timings'].values():
        assert set(row) == {'projection','directed_reachability_batch'}
        for stats in row.values():
            assert len(stats['observations_ns']) == 3
            assert stats['minimum_ns'] <= stats['median_ns'] <= stats['maximum_ns']


def test_invalid_repetition_budgets(miniature):
    for r,w in ((0,0),(2,2),(51,1),(3,-1),(3,11)):
        with pytest.raises(bb.BenchmarkError):
            bb.benchmark_graph(miniature,repeats=r,warmup=w)


def test_smoke_report_consistency():
    report = bb.make_report(profile='smoke', repeats=3, warmup=0)
    verified = bb.verify_report(report)
    assert verified['status'] == 'verified'
    assert verified['case_count'] == 2
    assert report['authority']['backend_auto_selection_permitted'] is False


def test_standard_profile_dimensions():
    assert len(bb.PROFILES['standard']) == 3
    assert bb.PROFILES['standard'][0][0] < bb.PROFILES['standard'][-1][0]


def test_manifest_fingerprint_deterministic():
    g = bb.generate_graph(16,100,5)
    assert bb.digest(g.to_dict()) == bb.digest(bb.generate_graph(16,100,5).to_dict())


def test_report_digest_tampering():
    report = bb.make_report(profile='smoke', repeats=3, warmup=0)
    report['cases'][0]['nodes'] += 1
    with pytest.raises(bb.BenchmarkError,match='digest'):
        bb.verify_report(report)


def test_authority_forgery_even_if_rehashed():
    report = bb.make_report(profile='smoke', repeats=3, warmup=0)
    report['authority']['scientific_approval_permitted'] = True
    report['report_sha256'] = bb.digest({k:v for k,v in report.items() if k != 'report_sha256'})
    with pytest.raises(bb.BenchmarkError,match='authority'):
        bb.verify_report(report)


def test_projection_loss_forgery_even_if_rehashed():
    report = bb.make_report(profile='smoke', repeats=3, warmup=0)
    report['cases'][0]['parity']['projection_capabilities']['scipy_sparse_matrix_lossless'] = True
    report['report_sha256'] = bb.digest({k:v for k,v in report.items() if k != 'report_sha256'})
    with pytest.raises(bb.BenchmarkError,match='source|loss-report'):
        bb.verify_report(report)


def test_altered_statistics_even_if_rehashed():
    report = bb.make_report(profile='smoke', repeats=3, warmup=0)
    report['cases'][0]['timings']['networkx']['projection']['median_ns'] += 1000
    report['report_sha256'] = bb.digest({k:v for k,v in report.items() if k != 'report_sha256'})
    with pytest.raises(bb.BenchmarkError,match='timing'):
        bb.verify_report(report)


def test_invalid_report_shape():
    with pytest.raises(bb.BenchmarkError):
        bb.verify_report({'schema_version':'different'})


def test_verified_persisted_state():
    repo = Path(__file__).resolve().parents[2]
    graph, state = bb._load_persisted(repo)
    assert graph.nodes
    assert state['head']
    result = bb.benchmark_graph(graph, repeats=3,warmup=0,scenario='persisted')
    assert result['parity']['status'] == 'verified'


def test_persisted_invalid_state(tmp_path):
    with pytest.raises((bb.BenchmarkError, ValueError)):
        bb._load_persisted(tmp_path)


def test_missing_persisted_repo():
    with pytest.raises(bb.BenchmarkError,match='repository'):
        bb.make_report(profile='smoke', repeats=3, warmup=0, persisted=True)


def test_cli_run_verify_roundtrip(tmp_path):
    output = tmp_path/'report.json'
    assert bb.main(['run','--profile','smoke','--repeats','3','--warmup','0','--report',str(output)]) == 0
    assert output.is_file()
    assert bb.main(['verify','--report',str(output)]) == 0
    assert bb.verify_report(__import__('json').loads(output.read_text()))['status'] == 'verified'


def test_report_never_selects_backend():
    obj = bb.make_report(profile='smoke',repeats=3,warmup=0)
    assert 'recommended_backend' not in obj
    assert obj['interpretation'].startswith('Observed')


def test_rehashed_synthetic_graph_forgery():
    report = bb.make_report(profile='smoke', repeats=3, warmup=0)
    report['cases'][0]['graph_sha256'] = '0'*64
    report['report_sha256'] = bb.digest({k:v for k,v in report.items() if k != 'report_sha256'})
    with pytest.raises(bb.BenchmarkError, match='source'):
        bb.verify_report(report)

def test_corrupted_scipy_side_channel(miniature):
    a = SciPyAdapter(miniature)
    a.metadata['edges'][0]['metadata'] = {'forged': True}
    with pytest.raises(bb.BenchmarkError,match='side-channel'):
        bb.verify_projection(miniature, NetworkXAdapter(miniature), a)
