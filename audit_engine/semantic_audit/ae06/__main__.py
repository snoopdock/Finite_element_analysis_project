"""Manual AE-06 command line interface: build, verify, and publish read-only evidence."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from .service import build_assessment
from .publication import publish_assessment, verify_assessment_publication


def main(argv=None):
    p=argparse.ArgumentParser(description='AE-06 bounded remediation/reintroduction evidence')
    p.add_argument('command', choices=['publish','verify'])
    p.add_argument('--output',type=Path,required=True)
    for arg in ('origin-before','flagged-output','current-output','origin-campaign','origin-review','followup-campaign'):
        p.add_argument('--'+arg,type=Path,required=True)
    p.add_argument('--history-output',type=Path,action='append',default=[])
    p.add_argument('--history-campaign',type=Path,action='append',default=[])
    p.add_argument('--origin-mutation-root',type=Path)
    p.add_argument('--followup-mutation-root',type=Path)
    p.add_argument('--replay-origin-mutation',action='store_true')
    p.add_argument('--replay-followup-mutation',action='store_true')
    args=p.parse_args(argv)
    inputs=dict(origin_before=args.origin_before,flagged_output=args.flagged_output,
                current_output=args.current_output,origin_campaign=args.origin_campaign,
                origin_review=args.origin_review,followup_campaign=args.followup_campaign,
                history_outputs=tuple(args.history_output),history_campaigns=tuple(args.history_campaign),origin_mutation_root=args.origin_mutation_root,
                followup_mutation_root=args.followup_mutation_root,
                replay_origin_mutation=args.replay_origin_mutation,
                replay_followup_mutation=args.replay_followup_mutation)
    try:
        result=(publish_assessment(build_assessment(**inputs),args.output,**inputs)
                if args.command=='publish' else verify_assessment_publication(args.output,**inputs))
        print(json.dumps(result,sort_keys=True))
        return 0 if result['status'] in ('bounded_absence_candidates_require_human_closure',
                                        'no_previous_violation_closure_claim') else 3
    except (ValueError,TypeError,RuntimeError,KeyError,IndexError,OSError) as exc:
        print(f'AE-06 error: {type(exc).__name__}: {exc}',file=sys.stderr)
        return 4

if __name__=='__main__':raise SystemExit(main())
