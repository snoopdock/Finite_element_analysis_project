import argparse
from pathlib import Path
import json
import yaml

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True)
    args = parser.parse_args()

    repo = Path(args.repository)
    schema = json.loads((repo / "decision_memory/outcome_schema.json").read_text())

    count = 0
    for f in (repo / "decision_memory/outcomes").glob("*.yaml"):
        record = yaml.safe_load(f.read_text())
        missing = [k for k in schema["required"] if k not in record]
        if missing:
            raise ValueError(f"{f.name}: missing {missing}")
        print("Validated outcome:", record["id"])
        count += 1

    if count == 0:
        raise ValueError("No outcome records found")

    print("Validated outcomes:", count)

if __name__ == "__main__":
    main()
