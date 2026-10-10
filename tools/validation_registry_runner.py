import argparse
import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone
import yaml

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--repository",required=True)
    p.add_argument("--profile",default="latest")
    args=p.parse_args()

    repo=Path(args.repository)
    profiles=sorted((repo/"validation/profiles").glob("*.yaml"))
    profile=profiles[-1] if args.profile=="latest" else repo/"validation/profiles"/(args.profile+".yaml")

    data=yaml.safe_load(profile.read_text())

    report={
        "profile_id": data["id"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repository": str(repo),
        "tests": data.get("target_tests", [])
    }

    digest=hashlib.sha256(json.dumps(report,sort_keys=True).encode()).hexdigest()
    report["report_sha256"]=digest

    out=repo/"validation"/"evidence_report.json"
    out.write_text(json.dumps(report,indent=2))

    print(json.dumps(report,indent=2))

if __name__=="__main__":
    main()
