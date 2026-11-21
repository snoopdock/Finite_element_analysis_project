from __future__ import annotations

import json
import os

from audit_engine.semantic_audit.core.semantic_graph import SemanticEdge, SemanticGraph, SemanticNode
from audit_engine.semantic_audit.graph.backend.snap_worker_adapter import SNAPWorkerAdapter


class _FakeStdin:
    def __init__(self, owner):
        self.owner = owner

    def write(self, value):
        self.owner.pending = value

    def flush(self):
        request = json.loads(self.owner.pending)
        operation = request["operation"]
        if operation == "init":
            result = {
                "graph_fingerprint": request["graph_fingerprint"],
                "node_count": len(request["nodes"]),
                "edge_occurrence_count": len(request["edges"]),
                "snap_version": "6.0.0-test-double",
                "python_version": "3.9.test-double",
                "platform": "isolated-test",
            }
        elif operation == "audit":
            nodes = request.get("nodes")
            # The fixture is deterministic and the fake process represents
            # the SNAP worker's native round-trip, not native acceptance.
            result = {
                "nodes": [
                    {"id": "a", "type": "Module", "attributes": {"path": "a.py"}, "metadata": {}},
                    {"id": "b", "type": "Module", "attributes": {"path": "b.py"}, "metadata": {}},
                ],
                "edges": [{
                    "native_edge_id": 17,
                    "occurrence": 0,
                    "source": "a",
                    "target": "b",
                    "relation": "CALLS",
                    "attributes": {"weight": 1},
                    "metadata": {"line": 3},
                }],
            }
        elif operation == "adjacency":
            result = {
                "records": [{
                    "native_edge_id": 17,
                    "occurrence": 0,
                    "source": "a",
                    "target": "b",
                    "relation": "CALLS",
                    "attributes": {"weight": 1},
                    "metadata": {"line": 3},
                }],
                "metrics": {
                    "native_adjacency_lookups": 1,
                    "outgoing_native_edge_id_lookups": 1,
                    "incoming_native_edge_id_lookups": 0,
                    "native_edge_occurrences_read": 1,
                },
            }
        elif operation == "metrics":
            result = {"metrics": {
                "native_adjacency_lookups": 1,
                "outgoing_native_edge_id_lookups": 1,
                "incoming_native_edge_id_lookups": 0,
                "native_edge_occurrences_read": 1,
            }}
        elif operation == "close":
            result = {"closed": True}
        else:
            raise AssertionError(operation)
        self.owner.output = json.dumps({
            "schema_version": "ae32c/snap-worker/v1",
            "request_id": request["request_id"],
            "status": "ok",
            "result": result,
        }) + "\n"

    def close(self):
        pass


class _FakeStdout:
    def __init__(self, owner):
        self.owner = owner

    def readline(self):
        result = self.owner.output
        self.owner.output = ""
        return result


class _FakeProcess:
    def __init__(self, command, **kwargs):
        self.command = command
        self.kwargs = kwargs
        self.pending = ""
        self.output = ""
        self.stdin = _FakeStdin(self)
        self.stdout = _FakeStdout(self)
        self.returncode = None

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        self.returncode = 0
        return 0

    def kill(self):
        self.returncode = -9


def _graph():
    graph = SemanticGraph()
    graph.add_node(SemanticNode("a", "Module", {"path": "a.py"}, {}))
    graph.add_node(SemanticNode("b", "Module", {"path": "b.py"}, {}))
    graph.add_edge(SemanticEdge("a", "b", "CALLS", {"weight": 1}, {"line": 3}))
    return graph


def test_snap_worker_adapter_uses_restricted_container_and_versioned_protocol(monkeypatch):
    captured = {}

    def fake_popen(command, **kwargs):
        process = _FakeProcess(command, **kwargs)
        captured["process"] = process
        return process

    monkeypatch.setenv("AE32C_SNAP_WORKER_IMAGE", "ae32c-snap-worker:test")
    monkeypatch.setattr("audit_engine.semantic_audit.graph.backend.snap_worker_adapter.shutil.which",
                        lambda name: "/usr/bin/docker")
    monkeypatch.setattr("audit_engine.semantic_audit.graph.backend.snap_worker_adapter.subprocess.Popen",
                        fake_popen)

    adapter = SNAPWorkerAdapter(_graph())
    assert adapter.worker_info["snap_version"] == "6.0.0-test-double"
    assert adapter.is_isolated_worker is True
    nodes = list(adapter.iter_native_nodes())
    edges = list(adapter.iter_native_edges())
    assert len(nodes) == 2
    assert edges == [{
        "occurrence": 0, "source": "a", "target": "b", "relation": "CALLS",
        "attributes": {"weight": 1}, "metadata": {"line": 3},
    }]
    adjacent = adapter.iter_adjacent_edge_occurrences("a", "outgoing")
    assert len(adjacent) == 1
    assert adjacent[0].occurrence_id == 0
    assert adjacent[0].backend_edge_ref == ("snap-worker", 17, 0)
    assert adapter.native_adjacency_report()["native_adjacency_lookups"] == 1

    process = captured["process"]
    command = process.command
    assert "--network=none" in command
    assert "--read-only" in command
    assert "--tmpfs" not in command
    assert "--cap-drop=ALL" in command
    assert "--security-opt=no-new-privileges" in command
    assert "--pull=never" in command
    assert not any(arg.startswith("-v") or arg == "--volume" for arg in command)
    assert process.kwargs["cwd"] != os.getcwd()
    assert set(process.kwargs["env"]) == {"PATH", "HOME"}
    adapter.close()
