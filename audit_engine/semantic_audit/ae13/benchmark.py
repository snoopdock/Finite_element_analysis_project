"""D3 reproducible workload generator with measured, environment-local cost.

Latency is reported as measurement, NOT a benchmark claim about the GitHub
runner or a memory-allocation guarantee. JSON bytes are serialized sizes,
not resident-set-size measurements.
"""
from __future__ import annotations
from collections import defaultdict
import platform
import statistics
import time

from .identity import canonical, content_id


def benchmark_relations(*, sources=120, observations_per_source=7, evidence_fanout=3,
                        runs=5, source_to_invalidate=0) -> dict:
    for v in (sources,observations_per_source,evidence_fanout,runs):
        if type(v) is not int or v < 1:
            raise ValueError('Benchmark bounds must be positive integers')
    if sources > 1500 or observations_per_source > 50 or evidence_fanout > 20 or runs > 30 or sources*observations_per_source*evidence_fanout > 20000:
        raise ValueError('Benchmark resource budget exceeded')
    if not 0<=source_to_invalidate<sources:
        raise ValueError('Missing selected source')
    source_ids=[f'file:{s}' for s in range(sources)]
    obs=[]; evid=[]; links=[]; obligations=[]
    for s in range(sources):
        for i in range(observations_per_source):
            oid=f'obs:{s}:{i}'
            obs.append({'id':oid,'source':source_ids[s],'relation':'SYNTACTIC_OBSERVATION'})
            # Same evidence can be linked to multiple observations, even across
            # sources, to stress shared dependency/invalidation indexes.
            for k in range(evidence_fanout):
                eid=f'ev:{(s*observations_per_source+i+k)//2}'
                evid.append({'id':eid,'sha256':content_id('simulated-evidence',[eid])})
                links.append({'observation':oid,'evidence':eid})
            obligations.append({'id':f'plan:{s}:{i}', 'observation':oid, 'source':source_ids[s]})
    e_map={e['id']:e for e in evid}
    normalized={'sources':source_ids,'observations':obs,'evidence':list(e_map.values()),
                'links':links,'obligations':obligations}
    links_by_obs=defaultdict(list)
    for l in links:links_by_obs[l['observation']].append(l['evidence'])
    duplicate={'obligations':[{'id':p['id'],'source':p['source'],
                'witnesses':[{'observation':p['observation'], 'evidence':e_map[eid]}
                            for eid in links_by_obs[p['observation']]]} for p in obligations]}
    obs_by_source=defaultdict(list); plans_by_obs=defaultdict(list)
    evidence_by_obs=defaultdict(set); obs_by_evidence=defaultdict(set)
    for o in obs:obs_by_source[o['source']].append(o['id'])
    for p in obligations:plans_by_obs[p['observation']].append(p['id'])
    for l in links:
        evidence_by_obs[l['observation']].add(l['evidence'])
        obs_by_evidence[l['evidence']].add(l['observation'])
    target=source_ids[source_to_invalidate]
    source_obs=set(obs_by_source[target])
    changed_evidence={eid for oid in source_obs for eid in evidence_by_obs[oid]}
    affected_obs=source_obs|{oid for eid in changed_evidence for oid in obs_by_evidence[eid]}
    expected={pid for oid in affected_obs for pid in plans_by_obs[oid]}
    timings={'scan_ms':[],'indexed_ms':[]}
    for _ in range(runs):
        t=time.perf_counter_ns()
        # Deliberately independent O(n) reference oracle; handles collateral
        # invalidation when another observation shares a changed witness.
        scanned_evidence={l['evidence'] for l in links if l['observation'] in source_obs}
        scanned_obs={l['observation'] for l in links if l['evidence'] in scanned_evidence}|source_obs
        scan={p['id'] for p in obligations if p['observation'] in scanned_obs}
        timings['scan_ms'].append((time.perf_counter_ns()-t)/1e6)
        t=time.perf_counter_ns()
        ids={pid for oid in affected_obs for pid in plans_by_obs[oid]}
        timings['indexed_ms'].append((time.perf_counter_ns()-t)/1e6)
        if scan!=ids or scan!=expected:
            raise AssertionError('Index differs from independent transitive invalidation')
    result={'schema':'ae13/relationship_benchmark/v1',
            'workload':{'source_count':sources,'observations_per_source':observations_per_source,
                        'evidence_fanout':evidence_fanout,'runs':runs,'source_to_invalidate':target},
            'counts':{'observations':len(obs),'unique_evidence':len(e_map),
                      'association_links':len(links),'verification_plans':len(obligations),
                      'invalidated_plans':len(expected),
                      'cross_source_invalidated_plans':sum(1 for p in obligations if p['id'] in expected and p['source']!=target)},
            'storage':{'normalized_json_bytes':len(canonical(normalized)),
                       'duplicated_json_bytes':len(canonical(duplicate)),
                       'definition':'canonical JSON bytes; not RSS, disk allocation or indexed database size'},
            'lookup':{k:{'median_ms':statistics.median(v),'samples_ms':v} for k,v in timings.items()},
            'environment':{'python':platform.python_version(),'platform':platform.platform()},
            'limits':['synthetic deterministic workload','no actual persistent database','timings are noisy and environment-specific',
                      'historical storage retention excludes compression/index overhead']}
    return result
