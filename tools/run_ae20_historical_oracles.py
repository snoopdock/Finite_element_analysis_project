"""Explicit, trusted manual invocation of the AE-20 pinned reference benchmark.

Do not run this with downloaded archives, PR-supplied code, or secrets in the
process environment. GitHub's authorized manual validation is the intended use.
"""
from __future__ import annotations
import argparse
from pathlib import Path
from audit_engine.semantic_audit.ae01.publication import canonical
from audit_engine.semantic_audit.ae20 import evaluate_trusted_historical_regressions


def main():
    parser=argparse.ArgumentParser(description='Trusted AE-20 regression reference replay (executes pinned historical code)')
    parser.add_argument('--authorize-trusted-replay', action='store_true', required=True)
    parser.add_argument('--fixtures', default='tests/semantic_audit/fixtures')
    parser.add_argument('--output', default=None)
    a=parser.parse_args()
    root=Path(a.fixtures).resolve()
    result=evaluate_trusted_historical_regressions(root/'ae20_faults'/'snapshots',
              root/'ae18_reference',root/'ae19_history',explicit_trusted_execution=a.authorize_trusted_replay)
    blob=canonical(result)
    if a.output:
        destination=Path(a.output).resolve()
        if destination.exists():
            raise FileExistsError('Do not overwrite historical reference outputs')
        if root==destination or root in destination.parents:
            raise ValueError('Output must be outside the reference corpus')
        destination.write_bytes(blob)
    else:
        print(blob.decode(),end='')
    if result['candidate_gate']!='pass_trusted_historical_regression_oracles_only':
        raise SystemExit(1)

if __name__=='__main__':
    main()
