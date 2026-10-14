"""Read-only AE-01 CLI. Exit 0: verified compliance; 2: verified defects; 3: incomplete; 4: execution error."""
import argparse
import json
import sys
from pathlib import Path
from .pipeline import audit_repository
from .publication import verify


def main(argv=None):
    parser = argparse.ArgumentParser(description='AE-01 source-bound architecture audit')
    parser.add_argument('--source-root', type=Path)
    parser.add_argument('--output-root', type=Path, required=True)
    parser.add_argument('--policy', type=Path)
    parser.add_argument('--lifecycle', type=Path, help='JSON object mapping module names to explicit lifecycle values')
    parser.add_argument('--exclude', action='append', default=[], help='Exact directory name')
    parser.add_argument('--verify', action='store_true', help='Verify latest sealed publication without executing an audit')
    args = parser.parse_args(argv)
    try:
        if args.verify:
            print(json.dumps(verify(args.output_root, source_root=args.source_root, policy_file=args.policy), sort_keys=True))
            return 0
        if not args.source_root or not args.policy or not args.lifecycle:
            parser.error('--source-root, --policy and --lifecycle are required for auditing')
        lifecycle = json.loads(args.lifecycle.read_text(encoding='utf-8'))
        if not isinstance(lifecycle, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in lifecycle.items()):
            raise ValueError('Lifecycle configuration must be a string-to-string JSON object')
        result = audit_repository(args.source_root, args.output_root, lifecycle=lifecycle,
                                  policy_file=args.policy, excludes=tuple(args.exclude))
        report = result['report']
        print(json.dumps({'run_id': report['run_id'], 'status': report['assurance_completeness'],
                          'findings': report['counts']['verified_findings'], 'issues': len(report['issues'])}, sort_keys=True))
        if report['assurance_completeness'] != 'complete_within_declared_scope':
            return 3
        return 2 if report['findings'] else 0
    except Exception as exc:
        print(f'AE-01 execution error: {type(exc).__name__}: {exc}', file=sys.stderr)
        return 4


if __name__ == '__main__':
    sys.exit(main())
