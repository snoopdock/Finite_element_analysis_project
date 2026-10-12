import argparse
import json
from pathlib import Path

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    snapshot = json.loads(Path(args.snapshot).read_text())

    nodes = snapshot.get("nodes", [])
    edges = snapshot.get("edges", [])

    impacted = {
        "source_snapshot": args.snapshot,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "impact_candidates": [
            {
                "node_id": n.get("id"),
                "reason": "reachable_dependency_candidate"
            }
            for n in nodes
        ]
    }

    Path(args.output).write_text(json.dumps(impacted, indent=2))
    print(json.dumps(impacted, indent=2))

if __name__ == "__main__":
    main()
