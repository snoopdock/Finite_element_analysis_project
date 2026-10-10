import argparse
import json
from pathlib import Path
from datetime import datetime, timezone

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True)
    parser.add_argument("--profile", default="latest")
    args = parser.parse_args()

    repo = Path(args.repository)
    profiles = sorted((repo / "validation" / "profiles").glob("*.yaml"))

    if not profiles:
        raise SystemExit("No validation profiles found")

    selected = profiles[-1] if args.profile == "latest" else repo / "validation" / "profiles" / f"{args.profile}.yaml"

    if not selected.exists():
        raise SystemExit(f"Profile not found: {selected}")

    entry = {
        "profile": selected.stem,
        "created_at": datetime.now(timezone.utc).isoformat()
    }

    catalog = repo / "validation-catalog" / "index.json"
    catalog.parent.mkdir(exist_ok=True)

    data = {"entries": []}
    if catalog.exists():
        data = json.loads(catalog.read_text())

    if entry not in data["entries"]:
        data["entries"].append(entry)

    catalog.write_text(json.dumps(data, indent=2))
    print(json.dumps(entry, indent=2))

if __name__ == "__main__":
    main()
