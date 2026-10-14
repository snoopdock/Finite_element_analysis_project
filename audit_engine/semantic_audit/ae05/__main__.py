"""Manual entrypoint for AE-05 review of sealed AE-04 campaigns."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
from . import initialize_review, append_review, verify_review_publication


def main(argv=None) -> int:
    p=argparse.ArgumentParser(description='AE-05 evidence-bound human review ledger')
    p.add_argument('command',choices=['init','record','verify'])
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--campaign-output',type=Path,required=True)
    p.add_argument('--before-output',type=Path,required=True)
    p.add_argument('--after-output',type=Path,required=True)
    p.add_argument('--mutation-root',type=Path)
    p.add_argument('--replay-mutation',action='store_true')
    p.add_argument('--obligation-id')
    p.add_argument('--action',choices=['acknowledge','requires_action','dispute'])
    p.add_argument('--actor')
    p.add_argument('--note')
    args=p.parse_args(argv)
    kw=dict(campaign_output=args.campaign_output,before_output=args.before_output,
            after_output=args.after_output,mutation_root=args.mutation_root,
            replay_mutation=args.replay_mutation)
    try:
        if args.command=='init':
            result=initialize_review(args.output,**kw)
        elif args.command=='record':
            if not all((args.obligation_id,args.action,args.actor,args.note)):
                raise ValueError('Manual review recording requires obligation ID, action, actor and note')
            result=append_review(args.output,obligation_id=args.obligation_id,
                                 action=args.action,actor=args.actor,note=args.note,**kw)
        else:
            result=verify_review_publication(args.output,**kw)
        print(json.dumps(result,sort_keys=True))
        if args.command == 'verify':
            return 0
        return 0 if result.get('review_state') == 'bounded_review_recorded' else 3
    except (ValueError,TypeError,KeyError,OSError,RuntimeError,IndexError) as exc:
        print(f'AE-05 review error: {type(exc).__name__}: {exc}',file=sys.stderr)
        return 4

if __name__=='__main__':
    raise SystemExit(main())
