#!/usr/bin/env python3
"""Isolated CPython 3.9 smoke for the published SNAP 6.0 TNEANet API.

This script intentionally imports no AE-32C code. It is a compatibility
probe for the future restricted worker, not native adapter acceptance.
"""
from __future__ import print_function
import argparse
import json
import platform
import sys
from pathlib import Path


def run():
    import snap

    graph = snap.TNEANet.New()
    graph.AddNode(101)
    graph.AddNode(202)
    first = graph.AddEdge(101, 202)
    second = graph.AddEdge(101, 202)
    graph.AddIntAttrE("semantic_occurrence")
    graph.AddIntAttrDatE(first, 0, "semantic_occurrence")
    graph.AddIntAttrDatE(second, 1, "semantic_occurrence")

    node = graph.GetNI(101)
    degree = int(node.GetOutDeg())
    neighbors = [int(node.GetOutNId(index)) for index in range(degree)]
    edge_records = []
    for edge in graph.Edges():
        edge_id = int(edge.GetId())
        edge_records.append({
            "edge_id": edge_id,
            "source": int(edge.GetSrcNId()),
            "target": int(edge.GetDstNId()),
            "semantic_occurrence": int(graph.GetIntAttrDatE(edge_id, "semantic_occurrence")),
        })

    if graph.GetNodes() != 2 or graph.GetEdges() != 2:
        raise RuntimeError("snap_tneanet_node_or_parallel_edge_count_mismatch")
    if degree != 2 or neighbors != [202, 202]:
        raise RuntimeError("snap_tneanet_outgoing_adjacency_mismatch")
    if [item["semantic_occurrence"] for item in edge_records] != [0, 1]:
        raise RuntimeError("snap_tneanet_edge_occurrence_mapping_mismatch")

    return {
        "schema_version": "ae32c/snap-python39-compatibility/v1",
        "status": "passed",
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "snap_module": getattr(snap, "__file__", None),
        "node_count": graph.GetNodes(),
        "edge_occurrence_count": graph.GetEdges(),
        "out_degree": degree,
        "out_neighbors": neighbors,
        "parallel_edge_occurrences": edge_records,
        "ae32c_adapter_acceptance": "not_run",
        "provider_calls_made": False,
        "network_calls_performed": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = run()
        code = 0
    except Exception as exc:
        report = {
            "schema_version": "ae32c/snap-python39-compatibility/v1",
            "status": "failed",
            "python_version": sys.version.split()[0],
            "failure_type": type(exc).__name__,
            "failure_message": str(exc)[:1000],
            "ae32c_adapter_acceptance": "not_run",
            "provider_calls_made": False,
        }
        code = 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
