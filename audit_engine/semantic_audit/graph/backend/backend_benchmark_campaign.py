"""G6.2: bounded multi-seed benchmark campaign with reproducible analysis.

This module summarizes *observed* G6.1 measurements. It does not certify timing
authenticity, statistical superiority, or authorize backend selection.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import statistics
from typing import Any

from . import backend_benchmark as bb

SCHEMA = 'g6-benchmark-campaign/v1'
AUTHORITY = {
    'backend_auto_selection_permitted': False,
    'scientific_truth_established': False,
    'scientific_approval_permitted': False,
    'graph_mutation_permitted': False,
    'performance_winner_established': False,
}
RECOMMENDATION = (
    'Descriptive multi-seed timings on this runner only. Paired observed ratios '
    'are not independent statistical trials; no confidence interval, universal '
    'winner or backend-selection authority is claimed.'
)


def _check_settings(profile: str, seeds: list[int], repeats: int, warmup: int) -> None:
    if profile not in bb.PROFILES:
        raise bb.BenchmarkError('Unknown campaign profile')
    if not isinstance(seeds, list) or not 2 <= len(seeds) <= 7 or any(
        type(x) is not int or not 0 <= x <= 2**32 - len(bb.PROFILES[profile])
        for x in seeds
    ) or len(seeds) != len(set(seeds)) or seeds != sorted(seeds):
        raise bb.BenchmarkError('Campaign requires 2–7 distinct ascending valid seeds')
    if type(repeats) is not int or not 3 <= repeats <= 20:
        raise bb.BenchmarkError('Campaign repeat budget must be 3–20')
    if type(warmup) is not int or not 0 <= warmup <= 5:
        raise bb.BenchmarkError('Campaign warmup budget must be 0–5')


def _median_ns(values: list[int | float]) -> int | float:
    return statistics.median(values)


def _metric_summary(values: list[int | float]) -> dict:
    """Descriptive across-seed median, min/max and median absolute deviation."""
    med = _median_ns(values)
    return {
        'sample_count': len(values),
        'median': med,
        'minimum': min(values),
        'maximum': max(values),
        'median_absolute_deviation': _median_ns([abs(v - med) for v in values]),
        'by_seed': list(values),
    }


def _summarize(reports: list[dict]) -> dict:
    count = len(reports[0]['cases'])
    summary = []
    for case_no in range(count):
        cases = [report['cases'][case_no] for report in reports]
        scenario = cases[0]['scenario']
        if any(case['scenario'] != scenario for case in cases):
            raise bb.BenchmarkError('Scenarios differ between campaign seeds')
        measurements: dict = {}
        for operation in ('projection', 'directed_reachability_batch'):
            values = {}
            for backend in ('networkx', 'scipy'):
                observed = [case['timings'][backend][operation]['median_ns'] for case in cases]
                values[backend] = _metric_summary(observed)
            pairs = []
            for nx_ns, sp_ns in zip(values['networkx']['by_seed'], values['scipy']['by_seed']):
                # The ratio is not meaningful if the observed denominator is zero.
                pairs.append(None if sp_ns == 0 else nx_ns / sp_ns)
            measurements[operation] = {
                'networkx_median_ns': values['networkx'],
                'scipy_median_ns': values['scipy'],
                'paired_nx_over_scipy_ratio': (
                    _metric_summary(pairs) if all(x is not None for x in pairs) else None
                ),
                'ratio_unavailable_due_to_zero_denominator': any(x is None for x in pairs),
            }
        summary.append({
            'scenario': scenario,
            'nodes': cases[0]['nodes'],
            'edge_occurrences': cases[0]['edge_occurrences'],
            'all_parity_verified': all(c['parity']['status'] == 'verified' for c in cases),
            'measurements': measurements,
        })
    # Scaling is a descriptive first-to-last comparison within a fixed profile.
    scales = {}
    synthetic_count = len(bb.PROFILES[reports[0]['profile']])
    if synthetic_count >= 2:
        first, last = summary[0], summary[synthetic_count - 1]
        for operation in ('projection', 'directed_reachability_batch'):
            scales[operation] = {}
            for backend in ('networkx', 'scipy'):
                key = f'{backend}_median_ns'
                a = first['measurements'][operation][key]['median']
                b = last['measurements'][operation][key]['median']
                scales[operation][backend] = {
                    'first_scenario': first['scenario'],
                    'last_scenario': last['scenario'],
                    'first_median_ns': a, 'last_median_ns': b,
                    'observed_last_over_first': None if a == 0 else b / a,
                }
    return {'cases': summary, 'scaling_observations': scales,
            'interpretation': RECOMMENDATION}


def _envelope(profile: str, seeds: list[int], repeats: int, warmup: int,
              reports: list[dict], summary: dict) -> dict:
    return {
        'schema_version': SCHEMA, 'profile': profile, 'seeds': seeds,
        'repeats': repeats, 'warmup': warmup,
        'source_report_sha256s': [r['report_sha256'] for r in reports],
        'runs': reports, 'summary': summary, 'authority': dict(AUTHORITY),
    }


def run_campaign(*, profile: str = 'standard', seeds: list[int] | None = None,
                 repeats: int = 5, warmup: int = 2,
                 repository: Path | None = None, persisted: bool = True) -> dict:
    seeds = [20261013, 20261014, 20261015] if seeds is None else seeds
    _check_settings(profile, seeds, repeats, warmup)
    if persisted and repository is None:
        raise bb.BenchmarkError('Persisted campaign requires a repository')
    reports = []
    for seed in seeds:
        report = bb.make_report(profile=profile, seed=seed, repeats=repeats,
                                warmup=warmup, repository=repository, persisted=persisted)
        bb.verify_report(report, repository=repository)
        reports.append(report)
    summary = _summarize(reports)
    document = _envelope(profile, seeds, repeats, warmup, reports, summary)
    document['report_sha256'] = bb.digest(document)
    return document



def _validate_child_shape(run: dict) -> None:
    """Deny supplementary claims inside otherwise valid G6.1 subreports."""
    if set(run) != {
        'schema_version', 'profile', 'seed', 'repeats', 'warmup', 'cases',
        'persisted_source', 'environment', 'authority', 'interpretation',
        'report_sha256',
    }:
        raise bb.BenchmarkError('Unexpected G6.1 child report fields')
    for case in run['cases']:
        if set(case) != {
            'scenario', 'graph_sha256', 'nodes', 'edge_occurrences',
            'parity', 'timings', 'scipy_csr_storage_bytes',
        } or set(case['timings']) != {'networkx', 'scipy'}:
            raise bb.BenchmarkError('Unexpected child scenario or backend fields')
        for backend_metrics in case['timings'].values():
            if set(backend_metrics) != {'projection', 'directed_reachability_batch'}:
                raise bb.BenchmarkError('Unexpected child measurement category')
            for m in backend_metrics.values():
                if set(m) != {
                    'unit', 'observations_ns', 'median_ns', 'p95_ns',
                    'minimum_ns', 'maximum_ns',
                }:
                    raise bb.BenchmarkError('Unexpected child measurement claims')


def verify_campaign(report: dict, *, repository: Path | None = None) -> dict:
    if not isinstance(report, dict) or report.get('schema_version') != SCHEMA:
        raise bb.BenchmarkError('Unknown campaign schema')
    payload = dict(report)
    observed_digest = payload.pop('report_sha256', None)
    if observed_digest != bb.digest(payload):
        raise bb.BenchmarkError('Campaign report digest mismatch')
    if payload.get('authority') != AUTHORITY:
        raise bb.BenchmarkError('Unauthorized campaign authority')
    profile, seeds = payload.get('profile'), payload.get('seeds')
    repeats, warmup = payload.get('repeats'), payload.get('warmup')
    _check_settings(profile, seeds, repeats, warmup)
    runs = payload.get('runs')
    if not isinstance(runs, list) or len(runs) != len(seeds):
        raise bb.BenchmarkError('Campaign run count mismatch')
    for run, seed in zip(runs, seeds):
        if not isinstance(run, dict):
            raise bb.BenchmarkError('Invalid embedded run')
        if any((run.get('profile') != profile, run.get('seed') != seed,
                run.get('repeats') != repeats, run.get('warmup') != warmup)):
            raise bb.BenchmarkError('Embedded run configuration mismatch')
        _validate_child_shape(run)
        bb.verify_report(run, repository=repository)
    if payload.get('source_report_sha256s') != [run['report_sha256'] for run in runs]:
        raise bb.BenchmarkError('Embedded run provenance mismatched')
    # Benchmark runs in a campaign must observe the same persisted state.
    if any(r.get('persisted_source') != runs[0].get('persisted_source') for r in runs):
        raise bb.BenchmarkError('Mixed persisted graph generations')
    envs = [r.get('environment') for r in runs]
    if any(env != envs[0] for env in envs):
        raise bb.BenchmarkError('Mixed runner environments')
    expected_summary = _summarize(runs)
    if payload.get('summary') != expected_summary:
        raise bb.BenchmarkError('Campaign summary or scaling results mismatch')
    if payload != _envelope(profile, seeds, repeats, warmup, runs, expected_summary):
        raise bb.BenchmarkError('Unexpected campaign fields or forgery')
    return {'schema_version': SCHEMA, 'status': 'verified',
            'report_sha256': observed_digest, 'run_count': len(runs),
            'case_count': len(runs[0]['cases']), 'parity': 'verified',
            'backend_auto_selection_permitted': False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='G6.2 multi-seed benchmark acceptance campaign')
    parser.add_argument('command', choices=('run','verify'))
    parser.add_argument('--profile', choices=tuple(bb.PROFILES), default='standard')
    parser.add_argument('--seeds', default='20261013,20261014,20261015',
                        help='2–7 distinct increasing comma-separated 32-bit integer seeds')
    parser.add_argument('--repeats', type=int, default=5)
    parser.add_argument('--warmup', type=int, default=2)
    parser.add_argument('--repository', default='.')
    parser.add_argument('--include-persisted', action='store_true')
    parser.add_argument('--report', required=True)
    args = parser.parse_args(argv)
    if args.command == 'run':
        try:
            seeds = [int(s) for s in args.seeds.split(',')]
        except ValueError as exc:
            raise bb.BenchmarkError('Invalid campaign seeds') from exc
        result = run_campaign(profile=args.profile, seeds=seeds, repeats=args.repeats,
                              warmup=args.warmup, repository=Path(args.repository),
                              persisted=args.include_persisted)
        dest = Path(args.report)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(bb.canonical(result))
        print(json.dumps({'status':'complete','report_sha256':result['report_sha256'],
                          'run_count':len(result['runs']),'case_count':len(result['runs'][0]['cases'])},sort_keys=True))
    else:
        result = json.loads(Path(args.report).read_bytes())
        print(json.dumps(verify_campaign(result, repository=Path(args.repository)), sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
