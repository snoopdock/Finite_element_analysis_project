#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Restricted JSON-lines worker for Stanford SNAP 6.0 / CPython 3.9.

The worker accepts only an immutable semantic graph snapshot and bounded
adjacency requests. It has no repository imports or file/provider APIs.
Container policy (network=none, read-only root, no capabilities) is enforced
by the orchestrator when it launches this process.
"""
from __future__ import print_function

import json
import platform
import sys

PROTOCOL = "ae32c/snap-worker/v1"
MAX_LINE_BYTES = 16 * 1024 * 1024
MAX_NODES = 200000
MAX_EDGES = 1000000\nMAX_ADJACENCY_OCCURRENCES = 100000

# Reserve stdout exclusively for protocol frames. Native-library diagnostics
# must never corrupt the JSON-lines channel.
_PROTOCOL_OUT = sys.stdout
sys.stdout = sys.stderr

_GRAPH = None
_NODE_ID_TO_NATIVE = {}
_NATIVE_TO_NODE_ID = {}
_EDGE_ID_TO_OCCURRENCE = {}
_OCCURRENCE_TO_EDGE_ID = {}
_NODES = []
_EDGES = []
_GRAPH_FINGERPRINT = None
_METRICS = {
    "native_adjacency_lookups": 0,
    "outgoing_native_edge_id_lookups": 0,
    "incoming_native_edge_id_lookups": 0,
    "native_edge_occurrences_read": 0,
}


def _fail(code):
    raise ValueError(code)


def _json_value(value, label):
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError):
        _fail(label + "_not_json_serializable")


def _init(message):
    global _GRAPH, _NODE_ID_TO_NATIVE, _NATIVE_TO_NODE_ID
    global _EDGE_ID_TO_OCCURRENCE, _OCCURRENCE_TO_EDGE_ID
    global _NODES, _EDGES, _GRAPH_FINGERPRINT, _METRICS

    if _GRAPH is not None:
        _fail("worker_already_initialized")
    nodes = message.get("nodes")
    edges = message.get("edges")
    fingerprint = message.get("graph_fingerprint")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        _fail("snapshot_nodes_or_edges_invalid")
    if len(nodes) > MAX_NODES or len(edges) > MAX_EDGES:
        _fail("snapshot_exceeds_worker_limits")
    if not isinstance(fingerprint, str) or len(fingerprint) != 64:
        _fail("graph_fingerprint_invalid")

    node_ids = set()
    for node in nodes:
        if not isinstance(node, dict):
            _fail("snapshot_node_invalid")
        ident = node.get("id")
        if not isinstance(ident, str) or not ident or ident in node_ids:
            _fail("snapshot_node_identity_invalid")
        if not isinstance(node.get("type"), str) or not node.get("type"):
            _fail("snapshot_node_type_invalid")
        _json_value(node.get("attributes"), "node_attributes")
        _json_value(node.get("metadata"), "node_metadata")
        node_ids.add(ident)

    occurrences = set()
    for index, edge in enumerate(edges):
        if not isinstance(edge, dict):
            _fail("snapshot_edge_invalid")
        if edge.get("source") not in node_ids or edge.get("target") not in node_ids:
            _fail("snapshot_edge_endpoint_invalid")
        if type(edge.get("occurrence")) is not int or edge.get("occurrence") != index:
            _fail("snapshot_edge_occurrence_invalid")
        if edge["occurrence"] in occurrences:
            _fail("snapshot_edge_occurrence_duplicate")
        occurrences.add(edge["occurrence"])
        if not isinstance(edge.get("relation"), str) or not edge.get("relation"):
            _fail("snapshot_edge_relation_invalid")
        _json_value(edge.get("attributes"), "edge_attributes")
        _json_value(edge.get("metadata"), "edge_metadata")

    # Import SNAP only inside the isolated worker runtime.
    import snap
    graph = snap.TNEANet.New()
    for name in ("semantic_id", "entity_type", "attributes_json", "metadata_json"):
        graph.AddStrAttrN(name)
    for name in ("relation", "attributes_json", "metadata_json"):
        graph.AddStrAttrE(name)
    graph.AddIntAttrE("semantic_occurrence")

    node_to_native = {}
    native_to_node = {}
    for index, node in enumerate(nodes):
        graph.AddNode(index)
        node_to_native[node["id"]] = index
        native_to_node[index] = node["id"]
        graph.AddStrAttrDatN(index, node["id"], "semantic_id")
        graph.AddStrAttrDatN(index, node["type"], "entity_type")
        graph.AddStrAttrDatN(index, _json_value(node["attributes"], "node_attributes"),
                             "attributes_json")
        graph.AddStrAttrDatN(index, _json_value(node["metadata"], "node_metadata"),
                             "metadata_json")

    edge_to_occurrence = {}
    occurrence_to_edge = {}
    for edge in edges:
        native_id = int(graph.AddEdge(node_to_native[edge["source"]],
                                      node_to_native[edge["target"]]))
        occurrence = edge["occurrence"]
        if native_id in edge_to_occurrence or occurrence in occurrence_to_edge:
            _fail("native_edge_identity_duplicate")
        edge_to_occurrence[native_id] = occurrence
        occurrence_to_edge[occurrence] = native_id
        graph.AddStrAttrDatE(native_id, edge["relation"], "relation")
        graph.AddStrAttrDatE(native_id, _json_value(edge["attributes"], "edge_attributes"),
                             "attributes_json")
        graph.AddStrAttrDatE(native_id, _json_value(edge["metadata"], "edge_metadata"),
                             "metadata_json")
        graph.AddIntAttrDatE(native_id, occurrence, "semantic_occurrence")

    if int(graph.GetNodes()) != len(nodes) or int(graph.GetEdges()) != len(edges):
        _fail("native_projection_count_mismatch")

    _GRAPH = graph
    _NODE_ID_TO_NATIVE = node_to_native
    _NATIVE_TO_NODE_ID = native_to_node
    _EDGE_ID_TO_OCCURRENCE = edge_to_occurrence
    _OCCURRENCE_TO_EDGE_ID = occurrence_to_edge
    _NODES = nodes
    _EDGES = edges
    _GRAPH_FINGERPRINT = fingerprint
    _METRICS = {
        "native_adjacency_lookups": 0,
        "outgoing_native_edge_id_lookups": 0,
        "incoming_native_edge_id_lookups": 0,
        "native_edge_occurrences_read": 0,
    }
    try:
        import importlib.metadata as metadata
        snap_version = metadata.version("snap-stanford")
    except Exception:
        snap_version = "unknown"
    return {
        "graph_fingerprint": fingerprint,
        "node_count": len(nodes),
        "edge_occurrence_count": len(edges),
        "occurrence_to_native_edge_id": [
            [occurrence, native_id]
            for occurrence, native_id in sorted(occurrence_to_edge.items())
        ],
        "snap_version": snap_version,
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
    }


def _edge_record(native_edge_id):
    native_edge_id = int(native_edge_id)
    if native_edge_id not in _EDGE_ID_TO_OCCURRENCE:
        _fail("native_adjacency_returned_unknown_edge_id")
    occurrence = _EDGE_ID_TO_OCCURRENCE[native_edge_id]
    if int(_GRAPH.GetIntAttrDatE(native_edge_id, "semantic_occurrence")) != occurrence:
        _fail("native_edge_occurrence_attribute_mismatch")
    edge = _GRAPH.GetEI(native_edge_id)
    source_native = int(edge.GetSrcNId())
    target_native = int(edge.GetDstNId())
    if source_native not in _NATIVE_TO_NODE_ID or target_native not in _NATIVE_TO_NODE_ID:
        _fail("native_edge_endpoint_unknown")
    source = _NATIVE_TO_NODE_ID[source_native]
    target = _NATIVE_TO_NODE_ID[target_native]
    relation = _GRAPH.GetStrAttrDatE(native_edge_id, "relation")
    attributes = json.loads(_GRAPH.GetStrAttrDatE(native_edge_id, "attributes_json"))
    metadata = json.loads(_GRAPH.GetStrAttrDatE(native_edge_id, "metadata_json"))
    canonical = _EDGES[occurrence]
    if (source != canonical["source"] or target != canonical["target"]
            or relation != canonical["relation"]
            or attributes != canonical["attributes"]
            or metadata != canonical["metadata"]):
        _fail("native_edge_payload_mismatch")
    return {
        "native_edge_id": native_edge_id,
        "occurrence": occurrence,
        "source": source,
        "target": target,
        "relation": relation,
        "attributes": attributes,
        "metadata": metadata,
    }


def _audit():
    observed_nodes = []
    for node in _GRAPH.Nodes():
        native_id = int(node.GetId())
        if native_id not in _NATIVE_TO_NODE_ID:
            _fail("audit_unknown_native_node")
        observed_nodes.append({
            "id": _GRAPH.GetStrAttrDatN(native_id, "semantic_id"),
            "type": _GRAPH.GetStrAttrDatN(native_id, "entity_type"),
            "attributes": json.loads(_GRAPH.GetStrAttrDatN(native_id, "attributes_json")),
            "metadata": json.loads(_GRAPH.GetStrAttrDatN(native_id, "metadata_json")),
        })
    observed_edges = []
    for edge in _GRAPH.Edges():
        observed_edges.append(_edge_record(int(edge.GetId())))
    observed_nodes.sort(key=lambda item: item["id"])
    observed_edges.sort(key=lambda item: item["occurrence"])
    return {"nodes": observed_nodes, "edges": observed_edges}


def _adjacency(message):
    node_id = message.get("node_id")
    direction = message.get("direction")
    if node_id not in _NODE_ID_TO_NATIVE:
        _fail("unknown_semantic_node_id")
    if direction not in ("outgoing", "incoming", "both"):
        _fail("adjacency_direction_invalid")
    node = _GRAPH.GetNI(_NODE_ID_TO_NATIVE[node_id])
    edge_ids = set()
    _METRICS["native_adjacency_lookups"] += 1
    if direction in ("outgoing", "both"):
        _METRICS["outgoing_native_edge_id_lookups"] += 1
        for index in range(int(node.GetOutDeg())):
            edge_ids.add(int(node.GetOutEId(index)))
    if direction in ("incoming", "both"):
        _METRICS["incoming_native_edge_id_lookups"] += 1
        for index in range(int(node.GetInDeg())):
            edge_ids.add(int(node.GetInEId(index)))
    records = [_edge_record(edge_id) for edge_id in sorted(edge_ids)]
    _METRICS["native_edge_occurrences_read"] += len(records)
    return {"records": records, "metrics": dict(_METRICS)}


def _handle(message):
    if not isinstance(message, dict):
        _fail("request_not_object")
    if message.get("schema_version") != PROTOCOL:
        _fail("protocol_version_mismatch")
    if not isinstance(message.get("request_id"), str) or not message.get("request_id"):
        _fail("request_id_invalid")
    operation = message.get("operation")
    common = {"schema_version", "request_id", "operation", "graph_fingerprint"}
    allowed = {
        "init": common | {"nodes", "edges"},
        "audit": common,
        "adjacency": common | {"node_id", "direction"},
        "metrics": common,
        "close": common,
    }
    if operation not in allowed or set(message) != allowed[operation]:
        _fail("request_schema_invalid")
    if operation == "init":
        return _init(message)
    if _GRAPH is None:
        _fail("worker_not_initialized")
    if message.get("graph_fingerprint") != _GRAPH_FINGERPRINT:
        _fail("graph_fingerprint_mismatch")
    if operation == "audit":
        return _audit()
    if operation == "adjacency":
        return _adjacency(message)
    if operation == "metrics":
        return {"metrics": dict(_METRICS)}
    if operation == "close":
        return {"closed": True}
    _fail("operation_not_allowed")


def main():
    while True:
        raw = sys.stdin.readline(MAX_LINE_BYTES + 1)
        if not raw:
            break
        request = None
        if len(raw.encode("utf-8")) > MAX_LINE_BYTES:
            response = {"status": "error", "error_code": "request_too_large"}
        else:
            try:
                request = json.loads(raw)
                request_id = request.get("request_id") if isinstance(request, dict) else None
                result = _handle(request)
                response = {
                    "schema_version": PROTOCOL,
                    "request_id": request_id,
                    "status": "ok",
                    "result": result,
                }
            except Exception as exc:
                response = {
                    "schema_version": PROTOCOL,
                    "request_id": request.get("request_id") if isinstance(request, dict) else None,
                    "status": "error",
                    "error_code": str(exc)[:300],
                    "error_type": type(exc).__name__,
                }
        _PROTOCOL_OUT.write(json.dumps(response, ensure_ascii=False, sort_keys=True,
                                       separators=(",", ":"), allow_nan=False) + "\n")
        _PROTOCOL_OUT.flush()
        if response.get("status") == "ok" and isinstance(request, dict) and request.get("operation") == "close":
            return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
