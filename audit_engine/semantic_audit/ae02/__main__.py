"""Read-only AE-02 CLI: compare independently sealed AE-01 audit generations."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from .service import compare_generations


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='AE-02 verified audit evolution comparison')
    parser.add_argument('--before-output', type=Path, required=True)
    parser.add_argument('--after-output', type=Path, required=True)
    parser.add_argument('--before-generation', help='Explicit historical AE-01 generation ID')
    parser.add_argument('--after-generation', help='Explicit historical AE-01 generation ID')
    parser.add_argument('--max-depth', type=int, default=32, help='Maximal static import propagation depth')
    parser.add_argument('--max-tasks', type=int, default=2500, help='Maximum listed review tasks')
    parser.add_argument('--verify-record', type=Path, help='Compare existing JSON record against independently rederived evidence')
    args = parser.parse_args(argv)
    try:
        comparison = compare_generations(
            args.before_output, args.after_output,
            before_generation=args.before_generation, after_generation=args.after_generation,
            max_depth=args.max_depth, max_tasks=args.max_tasks)
        if args.verify_record is not None:
            from audit_engine.semantic_audit.ae01.publication import canonical
            given = json.loads(args.verify_record.read_bytes())
            if canonical(given) != canonical(comparison):
                raise ValueError('Comparison record mismatch against independently verified generations')
            print('AE-02.1 detached comparison verification: passed')
        else:
            print(json.dumps(comparison, sort_keys=True, ensure_ascii=False))
        return 0 if (comparison['interpretation']['assurance_complete'] and
                     comparison['interpretation']['impact_plan_complete']) else 3
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f'AE-02 verification/comparison error: {type(exc).__name__}: {exc}', file=sys.stderr)
        return 4


if __name__ == '__main__':
    raise SystemExit(main())
