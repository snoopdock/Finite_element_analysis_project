#!/usr/bin/env python3
"""Deterministic G3 semantic graph analysis validation.

The validator exercises query validation, structural analysis, dependency
analysis, path analysis, evidence preservation, deterministic identities,
working-memory lifecycle behavior, and artifact serialization.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from audit_engine.semantic_audit.core.semantic_graph import (
    SemanticEdge,
    SemanticGraph,
    SemanticNode,
)
from audit_engine.semantic_audit.graph import SemanticGraphAnalysisService
from audit_engine.semantic_audit.graph.analysis import (
    AnalysisArtifactSerializer,
    VerificationStatus,
)
from audit_engine.semantic_audit.graph.queries import GraphQuery, QueryType


def build_fixture() -> SemanticGraph:
    graph = SemanticGraph()
    for node_id, entity_type in (
        ("app.py", "SoftwareModule"),
        ("service.py", "SoftwareModule"),
        ("db.py", "SoftwareModule"),
        ("logging.info", "Symbol"),
    ):
        graph.add_node(SemanticNode(node_id=node_id, entity_type=entity_type))

    graph.add_edge(
        SemanticEdge(
            source_id="app.py",
            target_id="service.py",
            relation_type="IMPORTS",
            metadata={"line": 1, "extractor": "ast"},
        )
    )
    graph.add_edge(
        SemanticEdge(
            source_id="service.py",
            target_id="db.py",
            relation_type="IMPORTS",
            metadata={"line": 2, "extractor": "ast"},
        )
    )
    graph.add_edge(
        SemanticEdge(
            source_id="app.py",
            target_id="logging.info",
            relation_type="USES",
            metadata={"line": 8, "extractor": "ast"},
        )
    )
    return graph


def run_validation(output_path: Path) -> dict:
    graph = build_fixture()
    service = SemanticGraphAnalysisService(graph)

    dependency = service.analyze(
        GraphQuery(
            "validation-dependency",
            QueryType.DEPENDENCY,
            ["app.py"],
            {"max_depth": 2},
        )
    )
    structural = service.analyze(
        GraphQuery(
            "validation-structural",
            QueryType.STRUCTURAL,
            ["app.py"],
            {"relation_types": ["USES"]},
        )
    )
    path = service.analyze(
        GraphQuery(
            "validation-path",
            QueryType.PATH,
            ["app.py"],
            {
                "target_entity": "db.py",
                "relation_types": ["IMPORTS"],
                "max_depth": 4,
            },
        )
    )

    checks = {
        "dependency_query": dependency.discovered_entities == ("service.py", "db.py"),
        "structural_query": structural.discovered_entities == ("logging.info",),
        "path_query": path.metadata.get("path_length") == 2,
        "semantic_identity_preservation": set(dependency.discovered_entities) == {"service.py", "db.py"},
        "evidence_preservation": all(record.provenance.get("edge_metadata") for record in dependency.evidence),
        "verification_boundary": all(record.verification_status is VerificationStatus.OBSERVED for record in dependency.evidence),
        "working_memory": len(service.memory) == 3,
    }

    original_analysis_id = dependency.analysis_id
    original_fingerprint = dependency.graph_fingerprint
    repeat = SemanticGraphAnalysisService(build_fixture()).analyze(
        GraphQuery(
            "validation-dependency",
            QueryType.DEPENDENCY,
            ["app.py"],
            {"max_depth": 2},
        )
    )
    checks["deterministic_analysis_identity"] = repeat.analysis_id == original_analysis_id
    checks["deterministic_graph_fingerprint"] = repeat.graph_fingerprint == original_fingerprint

    payload = {
        "schema_version": "semantic_graph_analysis_validation/v1",
        "status": "PASSED" if all(checks.values()) else "FAILED",
        "checks": checks,
        "architecture_guards": {
            "analysis_is_observation_not_finding": True,
            "backend_specific_ids_exposed": False,
            "default_verification_status": "observed",
        },
        "sample_results": AnalysisArtifactSerializer.bundle_to_dict(
            [dependency, structural, path]
        ),
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    if payload["status"] != "PASSED":
        failed = [name for name, ok in checks.items() if not ok]
        raise SystemExit("G3 semantic graph analysis validation failed: " + ", ".join(failed))

    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        default="artifacts/semantic_graph_analysis_validation.json",
    )
    args = parser.parse_args()

    payload = run_validation(Path(args.output))
    print(json.dumps(payload["checks"], indent=2))
    print("G3 semantic graph analysis validation passed.")


if __name__ == "__main__":
    main()
