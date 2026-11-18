#!/usr/bin/env python3
"""Read-only AE-32C E.7 graph inspection for the controlled repository snapshot."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from audit_engine.semantic_audit.ae32b import RepositoryEvidenceTools


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        default="tests/semantic_audit/fixtures/ae32c_provider_interface_incident",
        help="Repository or controlled fixture root.",
    )
    parser.add_argument(
        "--target",
        default="symbol:pipeline.extractor::extract",
        help="Exact graph node selector.",
    )
    parser.add_argument(
        "--relation-type",
        action="append",
        default=["CALLS"],
        help="Relation type to inspect. Repeat as needed.",
    )
    args = parser.parse_args()

    repo_root = Path(args.repo_root).expanduser().resolve()
    tools = RepositoryEvidenceTools(repo_root)
    relations = tuple(dict.fromkeys(item.strip() for item in args.relation_type if item.strip()))
    response = tools.invoke(
        "graph_neighbors",
        {
            "node": args.target,
            "direction": "both",
            "relation_types": list(relations),
            "max_depth": 1,
            "max_results": 20,
        },
    )
    payload = {
        "target": args.target,
        "requested_relation_types": list(relations),
        "repository_summary": tools.invoke("repository_summary", {}).get("result", {}),
        "graph_query": response,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    result = response.get("result", {}) if isinstance(response, dict) else {}
    observed = set(result.get("observed_relation_types", [])) if isinstance(result, dict) else set()
    if response.get("status") != "ok":
        return 2
    if not observed.intersection(relations):
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
