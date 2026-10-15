"""Manual-only operational evidence analyzer. Supplied outcomes are NOT authenticated."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from audit_engine.semantic_audit.ae16 import publish_observation,verify_observation


def main(argv=None):
    parser=argparse.ArgumentParser(description='AE-16 declared operational evidence observation and replay')
    parser.add_argument('--declaration',type=Path,required=True,help='Canonical JSON declaration')
    parser.add_argument('--evidence-root',type=Path,required=True)
    parser.add_argument('--output-root',type=Path,required=True)
    parser.add_argument('--ae01-output',type=Path,help='Optional AE-09 source correlation')
    parser.add_argument('--source-root',type=Path,help='Required with --ae01-output')
    parser.add_argument('--verify-only',action='store_true')
    args=parser.parse_args(argv)
    action=verify_observation if args.verify_only else publish_observation
    try:
        result=action(args.declaration,args.evidence_root,args.output_root,
                      ae01_output=args.ae01_output,source_root=args.source_root)
    except (ValueError,OSError,KeyError,TypeError) as exc:
        parser.exit(4,f'AE-16 failed: {type(exc).__name__}: {exc}\n')
    print(json.dumps(result,sort_keys=True,indent=2))
    return 0 if result['assurance']=='consistent_declared_observations_unattested' else 3


if __name__=='__main__':raise SystemExit(main())
