"""Read-only, source-only AE-22 benchmark runner; never executes target source."""
import argparse
from pathlib import Path
from audit_engine.semantic_audit.ae01.publication import canonical
from audit_engine.semantic_audit.ae22.evaluate import evaluate_casebook

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--casebook-root',type=Path,required=True)
    args=p.parse_args()
    result=evaluate_casebook(args.casebook_root)
    print(canonical(result).decode(),end='')
    # No threshold on detection rate. Failing samples are measurements, not CI failures.

if __name__=='__main__':main()
