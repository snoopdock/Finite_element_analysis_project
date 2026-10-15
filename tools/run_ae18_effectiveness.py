"""Manually requested bounded synthetic AE-16/17 effectiveness evaluation."""
import argparse,json
from pathlib import Path
from audit_engine.semantic_audit.ae18 import publish_evaluation,verify_evaluation

def main():
    parser=argparse.ArgumentParser(description='AE-18 controlled effectiveness; no real-world certification')
    parser.add_argument('--corpus',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--verify-only',action='store_true')
    parser.add_argument('--require-exact-controls',action='store_true')
    args=parser.parse_args()
    status=(verify_evaluation if args.verify_only else publish_evaluation)(args.corpus,args.output)
    print(json.dumps(status,sort_keys=True,indent=2))
    if args.require_exact_controls and status['candidate_gate']!='pass_controlled_reference_only':
        raise SystemExit(2)
if __name__=='__main__':main()
