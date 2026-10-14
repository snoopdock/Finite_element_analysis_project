"""Manual-only AE-04 campaign generation and detached verification."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
from . import build_campaign, publish_campaign, verify_publication


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='AE-04 conservative assurance campaign')
    parser.add_argument('command', choices=['run','verify'])
    parser.add_argument('--before-output', type=Path, required=True)
    parser.add_argument('--after-output', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--mutation-record', type=Path)
    parser.add_argument('--mutation-root', type=Path)
    parser.add_argument('--replay-mutation', action='store_true')
    parser.add_argument('--require-mutation', action='store_true')
    parser.add_argument('--max-depth', type=int, default=32)
    parser.add_argument('--max-tasks', type=int, default=2500)
    args = parser.parse_args(argv)
    try:
        if args.command == 'run':
            mutation = json.loads(args.mutation_record.read_bytes()) if args.mutation_record else None
            campaign = build_campaign(args.before_output, args.after_output,
                max_depth=args.max_depth, max_tasks=args.max_tasks,
                mutation_record=mutation, mutation_root=args.mutation_root,
                replay_mutation=args.replay_mutation, require_mutation=args.require_mutation)
            published = publish_campaign(campaign, args.output,
                before_output=args.before_output, after_output=args.after_output,
                mutation_root=args.mutation_root, replay_mutation=args.replay_mutation)
            print(json.dumps({'publication':published,'decision':campaign['decision']},sort_keys=True))
            return 0 if campaign['decision']['status'] == 'bounded_architecture_policy_pass' else 3
        result = verify_publication(args.output, before_output=args.before_output,
            after_output=args.after_output, mutation_root=args.mutation_root,
            replay_mutation=args.replay_mutation)
        print(json.dumps(result,sort_keys=True))
        return 0
    except (ValueError,TypeError,KeyError,OSError,RuntimeError,IndexError) as exc:
        print(f'AE-04 audit validation error: {type(exc).__name__}: {exc}',file=sys.stderr)
        return 4

if __name__ == '__main__':
    raise SystemExit(main())
