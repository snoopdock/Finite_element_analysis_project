"""Manual-only AE-10 CLI. Never alters authoritative sources."""
import argparse
import json
from .publication import publish_scientific_audit, verify_publication

def main():
    parser=argparse.ArgumentParser(description='Bounded scientific claim/evidence audit')
    subs=parser.add_subparsers(dest='command',required=True)
    for command in ('run','verify'):
        p=subs.add_parser(command)
        p.add_argument('--spec',required=True)
        p.add_argument('--artifacts-root',required=True)
        p.add_argument('--output',required=True)
    args=parser.parse_args()
    if args.command=='run':
        result=publish_scientific_audit(args.spec,args.artifacts_root,args.output)
    else:
        result=verify_publication(args.output,args.spec,args.artifacts_root)
    print(json.dumps(result,sort_keys=True))
    return 0 if result['verdict']=='consistent_within_declared_checks' else 2

if __name__=='__main__':
    raise SystemExit(main())
