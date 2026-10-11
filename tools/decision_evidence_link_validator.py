import argparse
from pathlib import Path
import yaml
import json

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--repository",required=True)
    args=p.parse_args()

    repo=Path(args.repository)
    schema=json.loads((repo/"decision_memory/link_schema.json").read_text())

    count=0
    for f in (repo/"decision_memory/links").glob("*.yaml"):
        item=yaml.safe_load(f.read_text())
        missing=[k for k in schema["required"] if k not in item]
        if missing:
            raise ValueError(f"{f.name}: missing {missing}")
        print("Validated link:", item["id"])
        count+=1

    if count == 0:
        raise ValueError("No decision evidence links found")

    print("Validated links:", count)

if __name__=="__main__":
    main()
