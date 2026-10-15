"""AE-09 manual, read-only investigation CLI."""
import argparse
import json
import sys
from pathlib import Path
from .publication import publish_investigation,verify_publication

def main(argv=None):
    parser=argparse.ArgumentParser(description='AE-09 bounded runtime failure correlation')
    parser.add_argument('--ae01-output',type=Path,required=True)
    parser.add_argument('--log-file',type=Path,required=True)
    parser.add_argument('--source-root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--generation-id',default=None)
    parser.add_argument('--max-depth',type=int,default=3)
    parser.add_argument('--max-candidates',type=int,default=250)
    parser.add_argument('--verify',action='store_true')
    args=parser.parse_args(argv)
    try:
        if args.verify:
            answer=verify_publication(args.output,args.ae01_output,args.log_file,args.source_root)
        else:
            answer=publish_investigation(args.ae01_output,args.log_file,args.source_root,args.output,
                                         generation_id=args.generation_id,max_depth=args.max_depth,
                                         max_candidates=args.max_candidates)
        print(json.dumps(answer,sort_keys=True))
        return 0 if answer['assurance_status']=='bounded_correlation' else 3
    except (ValueError,OSError,KeyError,TypeError) as exc:
        print(f'AE-09 investigation failed: {type(exc).__name__}: {exc}',file=sys.stderr)
        return 4

if __name__=='__main__':sys.exit(main())
