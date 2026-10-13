#!/usr/bin/env python3
"""True native library smoke test: checks graph structure AND stored properties.

Run in the Python interpreter where the optional backend is installed.
"""
import argparse
import json
from pathlib import Path

from audit_engine.semantic_audit.core.semantic_graph import SemanticGraph, SemanticNode, SemanticEdge
from audit_engine.semantic_audit.graph.backend.backend_factory import BackendFactory
from audit_engine.semantic_audit.graph.backend.execution_context import BackendExecutionContext


def _fixture():
    graph = SemanticGraph()
    graph.add_node(SemanticNode("alpha", "Concept", {"unicode": "λ", "value": 3}, {"source": "fem"}))
    graph.add_node(SemanticNode("beta", "Proposition", {"tags": ["x"]}, {"source": "paper"}))
    for rel, i in [("SUPPORTS", 1), ("REFERENCES", 2)]:
        graph.add_edge(SemanticEdge("alpha", "beta", rel, {"ordinal": i}, {"line": i}))
    graph.add_edge(SemanticEdge("beta", "beta", "REFLEXIVE", {"ordinal": 3}, {"line": 3}))
    return graph


def run(backend):
    graph = _fixture()
    adapter = BackendFactory().create(backend, BackendExecutionContext(graph))
    native = adapter.export()
    indices = adapter.identity_mapping()
    assert indices["semantic_to_backend"] == {"alpha": 0, "beta": 1}
    assert len(indices["semantic_edge_occurrence_to_backend"]) == 3
    assert adapter.neighbors("alpha") == ["beta"]
    assert adapter.neighbors("beta") == ["beta"]
    assert [e["relation"] for e in adapter.edges()] == ["SUPPORTS", "REFERENCES", "REFLEXIVE"]

    if backend == "igraph":
        assert native.is_directed() and native.vcount() == 2 and native.ecount() == 3
        assert native.get_edgelist() == [(0, 1), (0, 1), (1, 1)]
        assert native.vs["semantic_id"] == ["alpha", "beta"]
        assert native.es["relation"] == ["SUPPORTS", "REFERENCES", "REFLEXIVE"]
        assert native.vs["attributes"][0] == {"unicode": "λ", "value": 3}
        assert native.es["metadata"][2] == {"line": 3}
    elif backend == "graph-tool":
        assert native.is_directed() and native.num_vertices() == 2 and native.num_edges() == 3
        assert [(int(e.source()), int(e.target())) for e in native.edges()] == [(0, 1), (0, 1), (1, 1)]
        assert native.vertex_properties["semantic_id"][native.vertex(0)] == "alpha"
        assert native.vertex_properties["attributes"][native.vertex(0)] == {"unicode": "λ", "value": 3}
        actual = [(native.ep["relation"][e], native.ep["metadata"][e]) for e in native.edges()]
        assert actual == [("SUPPORTS", {"line": 1}), ("REFERENCES", {"line": 2}), ("REFLEXIVE", {"line": 3})]
    else:
        assert native.GetNodes() == 2 and native.GetEdges() == 3
        assert native.GetStrAttrDatN(0, "semantic_id") == "alpha"
        assert json.loads(native.GetStrAttrDatN(0, "attributes_json")) == {"unicode": "λ", "value": 3}
        edge_ids = indices["semantic_edge_occurrence_to_backend"]
        assert [native.GetStrAttrDatE(edge_ids[i], "relation") for i in range(3)] == [
            "SUPPORTS", "REFERENCES", "REFLEXIVE"
        ]
        assert json.loads(native.GetStrAttrDatE(edge_ids[2], "metadata_json")) == {"line": 3}
    return {"backend": backend, "status": "passed", "native_library_verified": True,
            "nodes": 2, "edge_occurrences": 3, "self_loops": 1, "parallel_edges": 2,
            "metadata_verified": True}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=["igraph", "graph-tool", "snap"], required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run(args.backend)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
