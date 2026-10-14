"""Manual CLI for verified review-only AE-07 portfolios."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

from audit_engine.semantic_audit.ae01.publication import _no_symlink_components
from .service import build_portfolio, _validated_entries
from .publication import publish_portfolio, verify_portfolio_publication


def main(argv=None):
    parser=argparse.ArgumentParser(description='AE-07 evidence-bound assurance portfolio (not release approval)')
    parser.add_argument('command',choices=('publish','verify'))
    parser.add_argument('--manifest',type=Path,required=True,
                        help='JSON object containing entries: [{assessment_output, inputs}]')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        _no_symlink_components(args.manifest.absolute())
        raw=json.loads(args.manifest.read_bytes())
        if not isinstance(raw,dict) or set(raw)!={'entries'}:
            raise ValueError('Manifest must contain only the entries array')
        entries=_validated_entries(raw['entries'])
        # Avoid having the output overwrite the user-supplied input manifest.
        from .publication import _path
        output=_path(args.output)
        manifest=_path(args.manifest)
        if output==manifest or output in manifest.parents or manifest in output.parents:
            raise ValueError('Publication output overlaps the input manifest')
        if args.command=='publish':
            result=publish_portfolio(build_portfolio(entries),args.output,entries=entries)
        else:
            result=verify_portfolio_publication(args.output,entries=entries)
        print(json.dumps(result,sort_keys=True))
        return 0 if result['status']=='bounded_evidence_ready_for_human_review' else 3
    except (ValueError,KeyError,IndexError,TypeError,OSError,RuntimeError) as exc:
        print(f'AE-07 error: {type(exc).__name__}: {exc}',file=sys.stderr)
        return 4

if __name__=='__main__':
    raise SystemExit(main())
