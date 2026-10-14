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
    args = parser.parse_args(argv)
    try:
        comparison = compare_generations(
            args.before_output, args.after_output,
            before_generation=args.before_generation, after_generation=args.after_generation)
        print(json.dumps(comparison, sort_keys=True, ensure_ascii=False))
        return 0 if comparison['interpretation']['assurance_complete'] else 3
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f'AE-02 verification/comparison error: {type(exc).__name__}: {exc}', file=sys.stderr)
        return 4


if __name__ == '__main__':
    raise SystemExit(main())
