from __future__ import annotations

import json
import os
import threading
import time

import pytest

from audit_engine.semantic_audit.core.semantic_graph import SemanticEdge, SemanticGraph, SemanticNode
from audit_engine.semantic_audit.graph.backend.snap_worker_adapter import (
    SNAPWorkerAdapter,
    SNAPWorkerProtocolError,
    SNAPWorkerTimeoutError,
)


class _FakeStdin:
    def __init__(self, owner):
        self.owner = owner

    def write(self, value):
        self.owner.pending = value

    def flush(self):
        request = json.loads(self.owner.pending)
        operation = request["operation"]
        self.owner.last_operation = operation
        if self.owner.block_flush_operation == operation:
            self.owner.flush_entered.set()
            self.owner.release_io.wait(timeout=3)
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
        self.owner.stdin_closed = True


class _FakeStdout:
    def __init__(self, owner):
        self.owner = owner

    def readline(self):
        if self.owner.block_read_operation == self.owner.last_operation:
            self.owner.read_entered.set()
            self.owner.release_io.wait(timeout=3)
        result = self.owner.output
        self.owner.output = ""
        return result

    def close(self):
        self.owner.stdout_closed = True


class _FakeProcess:
    def __init__(self, command, **kwargs):
        self.command = command
        self.kwargs = kwargs
        self.pending = ""
        self.output = ""
        self.stdin = _FakeStdin(self)
        self.stdout = _FakeStdout(self)
        self.returncode = None
        self.last_operation = None
        self.block_flush_operation = None
        self.block_read_operation = None
        self.release_io = threading.Event()
        self.flush_entered = threading.Event()
        self.read_entered = threading.Event()
        self.terminated = False
        self.killed = False
        self.events = []
        self.stdin_closed = False
        self.stdout_closed = False

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        self.returncode = 0
        return 0

    def terminate(self):
        self.events.append("docker-client-terminate")
        self.terminated = True
        self.returncode = -15
        self.release_io.set()

    def kill(self):
        self.events.append("docker-client-kill")
        self.killed = True
        self.returncode = -9
        self.release_io.set()


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
        if "--cidfile" in command:
            cidfile = command[command.index("--cidfile") + 1]
            with open(cidfile, "w", encoding="ascii") as handle:
                handle.write("fake-container-id")
        return process

    def fake_run(command, **kwargs):
        captured.setdefault("docker_calls", []).append((command, kwargs))
        process = captured.get("process")
        if process is not None:
            process.events.append("docker-rm-force")
            process.returncode = -9
            process.killed = True
            process.release_io.set()
        return type("Completed", (), {"returncode": 0})()

    monkeypatch.setattr(
        "audit_engine.semantic_audit.graph.backend.snap_worker_adapter.subprocess.run",
        fake_run,
    )
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
    assert "--ipc=none" in command
    assert "--read-only" in command
    assert "--tmpfs" not in command
    assert "--cap-drop=ALL" in command
    assert "--security-opt=no-new-privileges" in command
    assert "--pull=never" in command
    assert "--init" in command
    assert "--cidfile" in command
    assert os.path.isfile(command[command.index("--cidfile") + 1])
    assert not any(arg.startswith("-v") or arg == "--volume" for arg in command)
    assert process.kwargs["cwd"] != os.getcwd()
    assert set(process.kwargs["env"]) == {"PATH", "HOME"}
    adapter.close()



def _patch_fake_worker(monkeypatch, captured):
    def fake_popen(command, **kwargs):
        process = _FakeProcess(command, **kwargs)
        captured["process"] = process
        if "--cidfile" in command:
            cidfile = command[command.index("--cidfile") + 1]
            with open(cidfile, "w", encoding="ascii") as handle:
                handle.write("fake-container-id")
        return process

    def fake_run(command, **kwargs):
        captured.setdefault("docker_calls", []).append((command, kwargs))
        process = captured.get("process")
        if process is not None:
            process.events.append("docker-rm-force")
            process.returncode = -9
            process.killed = True
            process.release_io.set()
        return type("Completed", (), {"returncode": 0})()

    monkeypatch.setattr(
        "audit_engine.semantic_audit.graph.backend.snap_worker_adapter.subprocess.run",
        fake_run,
    )
    monkeypatch.setenv("AE32C_SNAP_WORKER_IMAGE", "ae32c-snap-worker:test")
    monkeypatch.setattr(
        "audit_engine.semantic_audit.graph.backend.snap_worker_adapter.shutil.which",
        lambda name: "/usr/bin/docker",
    )
    monkeypatch.setattr(
        "audit_engine.semantic_audit.graph.backend.snap_worker_adapter.subprocess.Popen",
        fake_popen,
    )


@pytest.mark.parametrize("blocked_phase", ("flush", "read"))
def test_snap_worker_request_deadline_bounds_pipe_io_and_discards_worker(
    monkeypatch, blocked_phase,
):
    captured = {}
    _patch_fake_worker(monkeypatch, captured)
    monkeypatch.setenv("AE32C_SNAP_WORKER_REQUEST_TIMEOUT_SECONDS", "0.05")
    adapter = SNAPWorkerAdapter(_graph())
    process = captured["process"]
    if blocked_phase == "flush":
        process.block_flush_operation = "audit"
        entered = process.flush_entered
    else:
        process.block_read_operation = "audit"
        entered = process.read_entered

    started = time.monotonic()
    with pytest.raises(SNAPWorkerTimeoutError, match="snap_worker_request_timeout:audit"):
        adapter._request("audit")
    elapsed = time.monotonic() - started

    assert entered.is_set()
    assert elapsed < 2.0
    assert process.killed
    assert captured["docker_calls"][0][0] == [
        "/usr/bin/docker", "rm", "--force", "fake-container-id",
    ]
    assert process.events[0] == "docker-rm-force"
    assert adapter._process is None
    with pytest.raises(SNAPWorkerProtocolError, match="snap_worker_process_not_running"):
        adapter._request("metrics")


def test_snap_worker_close_deadline_is_bounded(monkeypatch):
    captured = {}
    _patch_fake_worker(monkeypatch, captured)
    monkeypatch.setenv("AE32C_SNAP_WORKER_REQUEST_TIMEOUT_SECONDS", "0.05")
    adapter = SNAPWorkerAdapter(_graph())
    process = captured["process"]
    process.block_read_operation = "close"

    started = time.monotonic()
    adapter.close()
    elapsed = time.monotonic() - started

    assert process.read_entered.is_set()
    assert elapsed < 2.0
    assert process.killed
    assert captured["docker_calls"][0][0] == [
        "/usr/bin/docker", "rm", "--force", "fake-container-id",
    ]
    assert adapter._process is None


def test_snap_worker_timeout_configuration_is_finite_and_bounded(monkeypatch):
    monkeypatch.setenv("AE32C_SNAP_WORKER_IMAGE", "ae32c-snap-worker:test")
    monkeypatch.setenv("AE32C_SNAP_WORKER_REQUEST_TIMEOUT_SECONDS", "nan")
    monkeypatch.setattr(
        "audit_engine.semantic_audit.graph.backend.snap_worker_adapter.shutil.which",
        lambda name: "/usr/bin/docker",
    )
    with pytest.raises(ValueError, match="snap_worker_request_timeout_out_of_range"):
        SNAPWorkerAdapter(_graph())

    monkeypatch.setenv("AE32C_SNAP_WORKER_REQUEST_TIMEOUT_SECONDS", "601")
    with pytest.raises(ValueError, match="snap_worker_request_timeout_out_of_range"):
        SNAPWorkerAdapter(_graph())
