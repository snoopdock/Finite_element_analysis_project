import json
import pytest
from audit_engine.semantic_audit.ae13 import benchmark_relations


def test_d3_invalidation_and_serialization():
    r=benchmark_relations(sources=20,observations_per_source=5,evidence_fanout=3,runs=3)
    assert r['counts']['observations']==100
    assert r['counts']['association_links']==300
    assert r['counts']['invalidated_plans']>=5
    assert r['storage']['normalized_json_bytes']>0
    assert r['lookup']['indexed_ms']['median_ms']>=0
    assert r['lookup']['scan_ms']['median_ms']>=0
    assert 'not RSS' in r['storage']['definition']


def test_d3_different_fanout_and_workload():
    a=benchmark_relations(sources=10,observations_per_source=2,evidence_fanout=1,runs=2)
    b=benchmark_relations(sources=10,observations_per_source=2,evidence_fanout=3,runs=2)
    assert b['counts']['association_links']>a['counts']['association_links']
    assert b['counts']['invalidated_plans']>=a['counts']['invalidated_plans']


def test_d3_resource_boundaries():
    for kwargs in ({'sources':0},{'sources':2000},{'observations_per_source':0},{'evidence_fanout':21},
                   {'sources':1500,'observations_per_source':50,'evidence_fanout':20}, {'runs':0}):
        with pytest.raises(ValueError):benchmark_relations(**kwargs)


def test_d3_cli():
    import subprocess,sys
    p=subprocess.run([sys.executable,'-m','audit_engine.semantic_audit.ae13','benchmark','--sources','3','--observations','2'],capture_output=True,text=True,check=True)
    assert json.loads(p.stdout)['counts']['observations']==6


def test_cross_source_shared_evidence_invalidation_is_counted():
    report=benchmark_relations(sources=5,observations_per_source=2,evidence_fanout=3,runs=2)
    assert report['counts']['invalidated_plans']>2
    assert report['counts']['cross_source_invalidated_plans']>0
