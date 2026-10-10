import argparse
from pathlib import Path
import json
import yaml

def validate(record, schema):
    missing = [k for k in schema["required"] if k not in record]
    if missing:
        raise ValueError("Missing fields: " + ",".join(missing))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True)
    args = parser.parse_args()

    repo = Path(args.repository)
    schema = json.loads((repo/"decision_memory/schema.json").read_text())

    count = 0
    for item in (repo/"decision_memory/decisions").glob("*.yaml"):
        validate(yaml.safe_load(item.read_text()), schema)
        print("Validated decision:", item.name)
        count += 1

    if count == 0:
        raise SystemExit("No decision records found")

    print("Validated decision records:", count)

if __name__ == "__main__":
    main()
