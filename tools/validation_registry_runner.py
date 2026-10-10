import argparse
from pathlib import Path
import yaml
import json

def discover_profile(repo, requested):
    folder=Path(repo)/"validation"/"profiles"
    profiles=sorted(folder.glob("*.yaml"))
    if requested=="latest":
        return profiles[-1]
    return folder/(requested+".yaml")

def validate_schema(data, schema):
    for field in schema.get("required", []):
        if field not in data:
            raise ValueError(f"Missing required field: {field}")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--repository",required=True)
    p.add_argument("--profile",default="latest")
    args=p.parse_args()

    profile=discover_profile(args.repository,args.profile)
    schema=json.loads((Path(args.repository)/"validation/schema.json").read_text())
    data=yaml.safe_load(profile.read_text())
    validate_schema(data,schema)

    print("Validated profile:",data["id"])
    for test in data.get("target_tests",[]):
        print("Target:",test)

if __name__=="__main__":
    main()
