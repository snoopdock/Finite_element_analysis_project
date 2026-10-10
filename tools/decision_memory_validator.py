import argparse
from pathlib import Path
import yaml
import json

def validate(record, schema):
    missing = [k for k in schema.get("required", []) if k not in record]
    if missing:
        raise ValueError("Missing fields: " + ", ".join(missing))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True)
    args = parser.parse_args()

    repo = Path(args.repository)
    schema = json.loads((repo / "decision_memory/schema.json").read_text())

    decisions = repo / "decision_memory/decisions"

    validated = 0
    for item in decisions.glob("*.yaml"):
        record = yaml.safe_load(item.read_text())
        validate(record, schema)
        validated += 1
        print("Validated decision:", record["id"])

    print("Validated decision records:", validated)

if __name__ == "__main__":
    main()
