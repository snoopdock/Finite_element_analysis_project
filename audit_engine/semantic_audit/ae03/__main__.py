"""AE-03 explicit, manual read-only CLI. No automatic repository mutation."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
from .runner import run_experiment, verify_record
from audit_engine.semantic_audit.ae01.publication import canonical, _no_symlink_components, _atomic_bytes


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='AE-03 controlled mutation-oracle audit; trusted tests only')
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--source', action='append', default=[], help='Repository-relative Python source file (repeatable)')
    parser.add_argument('--test', action='append', default=[], help='Repository-relative tests/test_*.py (repeatable)')
    parser.add_argument('--max-mutants', type=int, default=20)
    parser.add_argument('--timeout', type=int, default=30)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--verify-report', type=Path)
    parser.add_argument('--replay', action='store_true')
    parser.add_argument('--before-ae01', type=Path)
    parser.add_argument('--after-ae01', type=Path)
    args = parser.parse_args(argv)
    try:
        if args.verify_report:
            if args.output or args.source or args.test:
                parser.error('--verify-report cannot be combined with audit-generation arguments')
            data = json.loads(args.verify_report.read_bytes())
            if bool(args.before_ae01) != bool(args.after_ae01):
                parser.error('Both AE-01 directories required for sealed impact verification')
            verified = None
            if args.before_ae01:
                from .impact import verified_impact
                verified = verified_impact(args.before_ae01, args.after_ae01)
            report = verify_record(data, args.repo, replay=args.replay,
                                   verified_impact_context=verified)
            print(json.dumps(report, sort_keys=True))
            return 0
        if not args.output or not args.source or not args.test:
            parser.error('--source, --test, and --output are required for experiments')
        if bool(args.before_ae01) != bool(args.after_ae01):
            parser.error('Both AE-01 generation directories must be provided for impact binding')
        impact = None
        if args.before_ae01:
            from .impact import verified_impact
            impact = verified_impact(args.before_ae01, args.after_ae01)
        report = run_experiment(args.repo, args.source, args.test,
                                max_mutants=args.max_mutants, timeout=args.timeout,
                                impact=impact)
        destination = args.output.absolute()
        _no_symlink_components(destination)
        # Do not publish reports into the authoritative input repository.
        if destination.is_relative_to(args.repo.resolve()):
            raise ValueError('Refusing audit report inside source repository')
        destination.parent.mkdir(parents=True, exist_ok=True)
        _atomic_bytes(destination, canonical(report))
        print(json.dumps({'assurance': report['assurance'], 'counts': report['counts'],
                          'report_sha256': report['record_sha256']}, sort_keys=True))
        return 0 if report['assurance'] == 'complete_for_selected_sites' else 3
    except (ValueError, TypeError, OSError, KeyError, UnicodeError, SyntaxError) as exc:
        print(f'AE-03 audit failure: {type(exc).__name__}: {exc}', file=sys.stderr)
        return 4


if __name__ == '__main__':
    raise SystemExit(main())
