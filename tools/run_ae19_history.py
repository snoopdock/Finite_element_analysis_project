"""Manually invoked read-only source replay of historical validation step logs."""
import argparse
import json
from audit_engine.semantic_audit.ae19 import publish_casebook


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--casebook',required=True)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    print(json.dumps(publish_casebook(args.casebook,args.output),sort_keys=True,indent=2))

if __name__=='__main__':main()
