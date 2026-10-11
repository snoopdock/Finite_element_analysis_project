import argparse
from pathlib import Path
import json
import yaml

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True)
    args = parser.parse_args()

    repo = Path(args.repository)
    schema = json.loads((repo/"decision_memory/action_schema.json").read_text())

    count = 0
    for f in (repo/"decision_memory/actions").glob("*.yaml"):
        record = yaml.safe_load(f.read_text())
        missing = [k for k in schema["required"] if k not in record]
        if missing:
            raise ValueError(f"{f.name}: missing {missing}")
        print("Validated action:", record["id"])
        count += 1

    if count == 0:
        raise ValueError("No SAT action records found")

    print("Validated SAT actions:", count)

if __name__ == "__main__":
    main()
