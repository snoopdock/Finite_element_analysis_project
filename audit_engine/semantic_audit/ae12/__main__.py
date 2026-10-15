"""Manually invoked, read-only AE-12 general code failure-mode audit."""
import argparse
import json
import sys
from pathlib import Path
from .publication import publish, verify_publication


def main(argv=None):
    parser=argparse.ArgumentParser(description='AE-12 evidence-bound Python failure-mode observations')
    parser.add_argument('--ae01-output',type=Path,required=True)
    parser.add_argument('--source-root',type=Path,required=True)
    parser.add_argument('--policy',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--generation-id')
    parser.add_argument('--runtime-log',type=Path)
    parser.add_argument('--verify',action='store_true')
    args=parser.parse_args(argv)
    try:
        if args.verify:
            report=verify_publication(args.output,args.ae01_output,args.source_root,args.policy,
                                      runtime_log=args.runtime_log)
        else:
            report=publish(args.ae01_output,args.source_root,args.policy,args.output,
                           runtime_log=args.runtime_log,generation_id=args.generation_id)
        print(json.dumps(report,sort_keys=True))
        return 0 if report['assurance_status']=='bounded_observations' else 3
    except (ValueError,KeyError,TypeError,OSError,UnicodeError) as exc:
        print(f'AE-12 failed: {type(exc).__name__}: {exc}',file=sys.stderr)
        return 4

if __name__=='__main__':
    sys.exit(main())
