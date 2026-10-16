"""AE-23: offline Git-tree admission and static assessment. No repository code execution.

Usage:
  python -m tools.run_ae23_assessment predict --lock LOCK.json --repository key=/repo
  python -m tools.run_ae23_assessment score --predictions PRED.json --reviews REV.json
  python -m tools.run_ae23_assessment verify --lock LOCK.json --repository key=/repo \
      --reviews REV.json --report REPORT.json

Score by itself never verifies input predictions. Use verify for independently
replayed complete results and compare exact canonical bytes.
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path
from audit_engine.semantic_audit.ae01.publication import canonical
from audit_engine.semantic_audit.ae23.admission import read_canonical
from audit_engine.semantic_audit.ae23.assessment import evaluate, predict, replay_equivalent, score


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command', required=True)
    for command in ('predict', 'score', 'verify'):
        p=sub.add_parser(command)
        if command in ('predict','verify'):
            p.add_argument('--lock',required=True,type=Path)
            p.add_argument('--repository',action='append',required=True,
                           help='KEY=/absolute/local/git/path (no network or checkout)')
        if command in ('score','verify'):
            p.add_argument('--reviews',required=True,type=Path)
        if command=='score':p.add_argument('--predictions',required=True,type=Path)
        if command=='verify':p.add_argument('--report',required=True,type=Path)
    args=parser.parse_args(argv)
    roots={}
    for item in getattr(args,'repository',[]) or []:
        if '=' not in item:parser.error('--repository must be KEY=PATH')
        key,path=item.split('=',1)
        if key in roots or not key or not path:parser.error('Duplicate or empty repository mapping')
        roots[key]=Path(path)
    if args.command=='predict':
        document=predict(args.lock,roots)
    elif args.command=='score':
        predictions,_=read_canonical(args.predictions)
        reviews,_=read_canonical(args.reviews)
        document=score(predictions,reviews)
    else:
        supplied,_=read_canonical(args.report)
        if not replay_equivalent(args.lock,roots,args.reviews,supplied):
            raise ValueError('Published assessment does not equal independent source replay')
        document={'schema':'ae23/verification_response/v1',
                  'comparison':'exact_replay_equivalent','source_origin_authenticated':False,
                  'verified_defects':0}
    sys.stdout.buffer.write(canonical(document))

if __name__=='__main__':main()
