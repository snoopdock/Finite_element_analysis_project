"""Manual-only source-bound AE-15 observation CLI. Does not evaluate target code."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from audit_engine.semantic_audit.ae15 import audit_flow_repository, verify_flow_repository


def main():
    p=argparse.ArgumentParser(description='AE-15 bounded may-flow observations, not verified findings')
    p.add_argument('--source-root',type=Path,required=True)
    p.add_argument('--output-root',type=Path,required=True)
    p.add_argument('--verify-only',action='store_true')
    args=p.parse_args()
    result=(verify_flow_repository(args.source_root,args.output_root) if args.verify_only else
            audit_flow_repository(args.source_root,args.output_root))
    print(json.dumps(result,sort_keys=True,indent=2))

if __name__=='__main__': main()
