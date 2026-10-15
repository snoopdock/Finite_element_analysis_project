"""Manual trusted CI runner for the code-pinned AE-21 pilot; NOT arbitrary Python execution."""
from __future__ import annotations
import argparse
from pathlib import Path
from audit_engine.semantic_audit.ae01.publication import canonical
from audit_engine.semantic_audit.ae21.evaluate import evaluate_pilot


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference-root',type=Path,required=True)
    parser.add_argument('--explicit-trusted-execution',action='store_true')
    args=parser.parse_args()
    result=evaluate_pilot(args.reference_root,explicit_trusted_execution=args.explicit_trusted_execution)
    print(canonical(result).decode(),end='')
    if result['pilot_gate']!='reference_oracles_reproduced':
        raise SystemExit(2)  # Oracle invalidity, not insufficient detector quality.

if __name__=='__main__':main()
