import argparse
import json
from pathlib import Path
from datetime import datetime, timezone

def catalog_path(repo):
    return Path(repo) / "validation-catalog" / "index.json"

def load_catalog(repo):
    p = catalog_path(repo)
    if not p.exists():
        return {"entries": []}
    return json.loads(p.read_text())

def add_entry(repo, entry):
    p = catalog_path(repo)
    p.parent.mkdir(parents=True, exist_ok=True)
    data = load_catalog(repo)
    for old in data["entries"]:
        if old.get("bundle_sha256") == entry.get("bundle_sha256"):
            return data
    data["entries"].append(entry)
    p.write_text(json.dumps(data, indent=2))
    return data

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True)
    parser.add_argument("--bundle-sha256", required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()

    entry = {
        "bundle_sha256": args.bundle_sha256,
        "profile": args.profile,
        "commit": args.commit,
        "created_at": datetime.now(timezone.utc).isoformat()
    }

    add_entry(args.repository, entry)
    print(json.dumps(entry, indent=2))

if __name__ == "__main__":
    main()
