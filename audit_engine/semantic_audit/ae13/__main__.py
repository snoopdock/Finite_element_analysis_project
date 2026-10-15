"""Manual-only read-only D1 / D3 CLI; no automatic workflows or code execution."""
import argparse
import json
import sys
from pathlib import Path
from .legacy import adapt_legacy, validate_legacy_report
from .benchmark import benchmark_relations


def main(argv=None):
    p=argparse.ArgumentParser(description='AE-13 D1-D3 independent design validation')
    sub=p.add_subparsers(dest='mode',required=True)
    a=sub.add_parser('legacy');a.add_argument('source_root',type=Path)
    a.add_argument('--path',action='append',dest='paths')
    b=sub.add_parser('benchmark');b.add_argument('--sources',type=int,default=120)
    b.add_argument('--observations',type=int,default=7)
    b.add_argument('--fanout',type=int,default=3)
    b.add_argument('--runs',type=int,default=5)
    args=p.parse_args(argv)
    try:
        if args.mode=='legacy':
            result=adapt_legacy(args.source_root,selected_paths=tuple(args.paths) if args.paths else None)
            validate_legacy_report(result,args.source_root)
        else:
            result=benchmark_relations(sources=args.sources,observations_per_source=args.observations,
                                       evidence_fanout=args.fanout,runs=args.runs)
        print(json.dumps(result,sort_keys=True,ensure_ascii=False))
        return 0
    except (ValueError,TypeError,OSError,RuntimeError) as exc:
        print(f'AE-13 design gate rejected input: {type(exc).__name__}: {exc}',file=sys.stderr)
        return 3
if __name__=='__main__':raise SystemExit(main())
