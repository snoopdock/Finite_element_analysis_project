"""Read-only-to-sources AE-17 entrypoint, writes sealed hypotheses to --output."""
from __future__ import annotations
import argparse
import json
from audit_engine.semantic_audit.ae17 import publish_investigation, verify_investigation

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--declaration',required=True)
    ap.add_argument('--evidence-root',required=True)
    ap.add_argument('--ae16-output',required=True)
    ap.add_argument('--output',required=True)
    ap.add_argument('--ae01-output')
    ap.add_argument('--source-root')
    ap.add_argument('--max-cases',type=int,default=80)
    ap.add_argument('--max-context',type=int,default=64)
    ap.add_argument('--verify-only',action='store_true')
    args=ap.parse_args()
    if bool(args.ae01_output)!=bool(args.source_root):ap.error('AE-01 output and source root must be provided together')
    kw={'ae01_output':args.ae01_output,'source_root':args.source_root}
    op=verify_investigation if args.verify_only else publish_investigation
    if args.verify_only:out=op(args.declaration,args.evidence_root,args.ae16_output,args.output,**kw)
    else:out=op(args.declaration,args.evidence_root,args.ae16_output,args.output,
                max_cases=args.max_cases,max_context=args.max_context,**kw)
    print(json.dumps(out,sort_keys=True,indent=2))

if __name__=='__main__':main()
