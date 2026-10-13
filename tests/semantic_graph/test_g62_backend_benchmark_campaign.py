"""G6.2 regression: multi-seed experiment, replay, boundaries, recomputation."""
import copy
import json
from pathlib import Path

import pytest

from audit_engine.semantic_audit.graph.backend import backend_benchmark as bb
from audit_engine.semantic_audit.graph.backend import backend_benchmark_campaign as campaign
from audit_engine.semantic_audit.graph.persistent_domain_state import GraphStoreError


@pytest.fixture(scope='module')
def two_seed():
    return campaign.run_campaign(profile='smoke', seeds=[7, 8], repeats=3,
                                 warmup=0, persisted=False)


def rehash(document):
    document['report_sha256'] = bb.digest({k: v for k, v in document.items() if k != 'report_sha256'})
    return document


def rehash_child(document, index=0):
    child = document['runs'][index]
    child['report_sha256'] = bb.digest({k: v for k, v in child.items() if k != 'report_sha256'})
    document['source_report_sha256s'][index] = child['report_sha256']
    return rehash(document)


def test_campaign_reconstructs_and_accepts(two_seed):
    assert campaign.verify_campaign(two_seed)['status'] == 'verified'
    assert campaign.verify_campaign(two_seed)['run_count'] == 2


def test_campaign_semantic_parity_per_seed(two_seed):
    for run in two_seed['runs']:
        assert bb.verify_report(run)['status'] == 'verified'
        assert all(case['parity']['status'] == 'verified' for case in run['cases'])


def test_seeded_inputs_are_distinct(two_seed):
    assert two_seed['runs'][0]['cases'][0]['graph_sha256'] != two_seed['runs'][1]['cases'][0]['graph_sha256']


def test_campaign_report_has_no_winner(two_seed):
    assert not two_seed['authority']['backend_auto_selection_permitted']
    assert not two_seed['authority']['performance_winner_established']
    assert 'winner' not in two_seed['summary']


def test_metric_aggregation_mathematically_correct(two_seed):
    for case_num, summary in enumerate(two_seed['summary']['cases']):
        for operation in ('projection', 'directed_reachability_batch'):
            for backend in ('networkx', 'scipy'):
                data = summary['measurements'][operation][f'{backend}_median_ns']
                assert data['by_seed'] == [r['cases'][case_num]['timings'][backend][operation]['median_ns'] for r in two_seed['runs']]
                assert data['sample_count'] == 2
                assert data['minimum'] <= data['median'] <= data['maximum']


def test_scale_profile_correct(two_seed):
    scale = two_seed['summary']['scaling_observations']['projection']
    assert scale['scipy']['first_scenario'] == 'synthetic_16_55'
    assert scale['scipy']['last_scenario'] == 'synthetic_64_260'


@pytest.mark.parametrize('seeds',[[],[1],[1,1],[2,1],[-1,2],['2',3],[1.0,2],list(range(8)),[2**32,2**32+1]])
def test_rejects_bad_seed_set(seeds):
    with pytest.raises(bb.BenchmarkError,match='seed'):
        campaign.run_campaign(profile='smoke',seeds=seeds,repeats=3,warmup=0,persisted=False)


@pytest.mark.parametrize('repeats,warmup', [(0,0),(2,0),(21,0),(True,0),(3,-1),(3,6),(3,False)])
def test_rejects_unsafe_budget(repeats,warmup):
    with pytest.raises(bb.BenchmarkError,match='budget'):
        campaign.run_campaign(profile='smoke',seeds=[1,2],repeats=repeats,warmup=warmup,persisted=False)


def test_rejects_invalid_profile():
    with pytest.raises(bb.BenchmarkError,match='profile'):
        campaign.run_campaign(profile='unknown', seeds=[1,2], persisted=False)


def test_requires_repository_in_persisted_mode():
    with pytest.raises(bb.BenchmarkError,match='repository'):
        campaign.run_campaign(profile='smoke',seeds=[1,2],persisted=True)


def test_digest_mutation(two_seed):
    data = copy.deepcopy(two_seed)
    data['summary']['cases'][0]['nodes'] = 999
    with pytest.raises(bb.BenchmarkError, match='digest'):
        campaign.verify_campaign(data)


def test_rehashed_summary_forgery(two_seed):
    data=copy.deepcopy(two_seed)
    data['summary']['cases'][0]['measurements']['projection']['networkx_median_ns']['median'] += 5
    rehash(data)
    with pytest.raises(bb.BenchmarkError,match='summary'):
        campaign.verify_campaign(data)


def test_rehashed_scaling_forgery(two_seed):
    data=copy.deepcopy(two_seed)
    data['summary']['scaling_observations']['projection']['scipy']['observed_last_over_first'] = 8.0
    rehash(data)
    with pytest.raises(bb.BenchmarkError,match='summary'):
        campaign.verify_campaign(data)


def test_rehashed_wrong_seed(two_seed):
    data=copy.deepcopy(two_seed)
    data['seeds'] = [7,9]
    rehash(data)
    with pytest.raises(bb.BenchmarkError,match='configuration'):
        campaign.verify_campaign(data)


def test_rehashed_graph_forgery(two_seed):
    data=copy.deepcopy(two_seed)
    data['runs'][0]['cases'][0]['graph_sha256']='0'*64
    rehash_child(data)
    with pytest.raises(bb.BenchmarkError,match='source'):
        campaign.verify_campaign(data)


def test_rehashed_parity_forgery(two_seed):
    data=copy.deepcopy(two_seed)
    data['runs'][0]['cases'][0]['parity']['multiedge_occurrences'] += 1
    rehash_child(data)
    with pytest.raises(bb.BenchmarkError,match='source'):
        campaign.verify_campaign(data)


def test_rehashed_authority_forgery(two_seed):
    data=copy.deepcopy(two_seed)
    data['authority']['backend_auto_selection_permitted']=True
    rehash(data)
    with pytest.raises(bb.BenchmarkError,match='authority'):
        campaign.verify_campaign(data)


def test_rehashed_injected_winner(two_seed):
    data=copy.deepcopy(two_seed)
    data['recommended_backend']='scipy'
    rehash(data)
    with pytest.raises(bb.BenchmarkError,match='Unexpected'):
        campaign.verify_campaign(data)



def test_rehashed_injected_winner_inside_child(two_seed):
    data = copy.deepcopy(two_seed)
    data['runs'][0]['recommended_backend'] = 'networkx'
    rehash_child(data)
    with pytest.raises(bb.BenchmarkError, match='Unexpected G6.1 child'):
        campaign.verify_campaign(data)


def test_rehashed_injected_backend_timing(two_seed):
    data = copy.deepcopy(two_seed)
    data['runs'][0]['cases'][0]['timings']['fabricated'] = {}
    rehash_child(data)
    with pytest.raises(bb.BenchmarkError, match='Unexpected child'):
        campaign.verify_campaign(data)


def test_rehashed_child_digest_forgery(two_seed):
    data=copy.deepcopy(two_seed)
    data['source_report_sha256s'][0]='0'*64
    rehash(data)
    with pytest.raises(bb.BenchmarkError,match='provenance'):
        campaign.verify_campaign(data)


def test_rehashed_environment_mismatch(two_seed):
    data=copy.deepcopy(two_seed)
    data['runs'][1]['environment']['python']='0.0'
    rehash_child(data,1)
    with pytest.raises(bb.BenchmarkError,match='environments'):
        campaign.verify_campaign(data)


def test_rehashed_persisted_state_mix(two_seed):
    data=copy.deepcopy(two_seed)
    data['runs'][0]['persisted_source']={'forged':True}
    rehash_child(data)
    with pytest.raises(bb.BenchmarkError):
        campaign.verify_campaign(data)


def test_rehashed_wrong_number_of_runs(two_seed):
    data=copy.deepcopy(two_seed)
    data['runs'].pop()
    rehash(data)
    with pytest.raises(bb.BenchmarkError,match='count'):
        campaign.verify_campaign(data)


def test_wrong_schema(two_seed):
    data=copy.deepcopy(two_seed)
    data['schema_version']='g0'
    rehash(data)
    with pytest.raises(bb.BenchmarkError,match='schema'):
        campaign.verify_campaign(data)


def test_real_persisted_graph(tmp_path):
    repo=Path(__file__).resolve().parents[2]
    result=campaign.run_campaign(profile='smoke',seeds=[100,101],repeats=3,warmup=0,
                                 persisted=True,repository=repo)
    assert len(result['runs'][0]['cases'])==3
    assert campaign.verify_campaign(result, repository=repo)['case_count']==3
    assert result['runs'][0]['persisted_source']==result['runs'][1]['persisted_source']


def test_cli_run_verify(tmp_path):
    outfile=tmp_path/'benchmark.json'
    assert campaign.main(['run','--profile','smoke','--seeds','12,13','--repeats','3',
                          '--warmup','0','--report',str(outfile)])==0
    assert campaign.main(['verify','--report',str(outfile)])==0
    assert campaign.verify_campaign(json.loads(outfile.read_text()))['status']=='verified'


def test_cli_persisted_source(tmp_path):
    outfile=tmp_path/'benchmark.json'
    repo=Path(__file__).resolve().parents[2]
    args=['--report',str(outfile),'--repository',str(repo)]
    assert campaign.main(['run','--profile','smoke','--seeds','12,13','--repeats','3',
                          '--warmup','0','--include-persisted',*args])==0
    assert campaign.main(['verify',*args])==0


def test_missing_source_is_not_treated_as_zero():
    with pytest.raises((bb.BenchmarkError, GraphStoreError)):
        campaign.run_campaign(profile='smoke', seeds=[1,2], repeats=3,
                              persisted=True, repository=Path('/nonexistent/g6.2'))


def test_summary_is_deterministic_from_same_child_reports(two_seed):
    assert campaign._summarize(two_seed['runs']) == two_seed['summary']


def test_ratio_is_null_for_zero_denominator():
    reports=[]
    for seed in [1,2]:
        r=bb.make_report(profile='smoke',seed=seed,repeats=3,warmup=0)
        r['cases'][0]['timings']['scipy']['projection']['median_ns']=0
        reports.append(r)
    result=campaign._summarize(reports)
    ratio=result['cases'][0]['measurements']['projection']
    assert ratio['paired_nx_over_scipy_ratio'] is None
    assert ratio['ratio_unavailable_due_to_zero_denominator']
