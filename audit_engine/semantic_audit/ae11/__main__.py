"""Manual, read-only FEM evidence audit and detached verifier."""
import argparse
import json
from .publication import publish, verify_publication

def main():
    p=argparse.ArgumentParser(description='AE-11 bounded FEM numerical invariant audit')
    sub=p.add_subparsers(dest='command',required=True)
    for op in ('run','verify'):
        sp=sub.add_parser(op)
        sp.add_argument('--spec',required=True)
        sp.add_argument('--artifacts-root',required=True)
        sp.add_argument('--output',required=True)
    args=p.parse_args()
    result = (publish(args.spec,args.artifacts_root,args.output) if args.command=='run' else
              verify_publication(args.output,args.spec,args.artifacts_root))
    print(json.dumps(result,sort_keys=True))
    return 0 if result['verdict']=='consistent_within_declared_checks' else 2

if __name__=='__main__':
    raise SystemExit(main())
