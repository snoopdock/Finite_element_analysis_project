"""Read-only evaluator CLI; only explicit outputs are written."""
import argparse
import json
from pathlib import Path
import sys

from .benchmark import evaluate, verify_result, survey, write_report


def main(argv=None):
    p = argparse.ArgumentParser(description='AE-08 bounded effectiveness evaluation')
    p.add_argument('command', choices=('evaluate', 'verify', 'survey'))
    p.add_argument('--source-root', type=Path, required=True)
    p.add_argument('--gold', type=Path)
    p.add_argument('--policy', type=Path)
    p.add_argument('--audit-output', type=Path)
    p.add_argument('--report', type=Path)
    p.add_argument('--exclude', action='append', default=[])
    args = p.parse_args(argv)
    try:
        if args.command == 'survey':
            if args.gold or args.policy or args.audit_output:
                raise ValueError('Unlabeled survey must not accept gold or audit generation')
            result = survey(args.source_root, excludes=tuple(args.exclude))
        else:
            if not all((args.gold, args.policy, args.audit_output)):
                raise ValueError('Gold, policy, and audit output are required')
            if args.command == 'evaluate':
                result = evaluate(args.source_root, args.gold, args.policy, args.audit_output)
            else:
                if not args.report or not args.report.is_file():
                    raise ValueError('Existing benchmark report is required for verification')
                result = verify_result(json.loads(args.report.read_bytes()), args.source_root,
                                       args.gold, args.policy, args.audit_output)
        if args.report and args.command != 'verify':
            write_report(args.report, result)
        print(json.dumps(result, sort_keys=True))
        if args.command == 'evaluate':
            return 0 if result['all_gold_annotations_matched'] else 2
        return 0
    except (ValueError, KeyError, OSError, TypeError, json.JSONDecodeError) as exc:
        print(f'AE-08 error: {type(exc).__name__}: {exc}', file=sys.stderr)
        return 4

if __name__ == '__main__':
    raise SystemExit(main())
