"""Python 3.11 proxy for the isolated CPython 3.9 SNAP worker.

The SNAP native module is never imported into the project interpreter. A
minimal Docker container receives only a JSON graph snapshot and bounded
adjacency requests. The container has no network, no repository mount, a
read-only root filesystem and no Linux capabilities.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from copy import deepcopy
from typing import Any

from audit_engine.semantic_audit.core.semantic_graph import SemanticGraph
from audit_engine.semantic_audit.graph.analysis.identity import graph_fingerprint
from audit_engine.semantic_audit.graph.analysis.models import TraversalDirection
from audit_engine.semantic_audit.graph.backend.adapter_interface import (
    NativeEdgeOccurrence,
    SemanticGraphAdapter,
)
from audit_engine.semantic_audit.graph.backend.optional_backend_support import (
    NativeAdapterMixin,
    make_projection,
)


class SNAPWorkerProtocolError(RuntimeError):
    """The isolated worker returned a malformed or unsuccessful protocol frame."""


class SNAPWorkerAdapter(NativeAdapterMixin, SemanticGraphAdapter):
    """Native TNEANet adapter whose implementation runs only in the worker."""

    backend_name = "snap"
    is_isolated_worker = True
    PROTOCOL = "ae32c/snap-worker/v1"

    def __init__(self, graph: SemanticGraph):
        if not isinstance(graph, SemanticGraph):
            raise TypeError("SNAPWorkerAdapter requires a SemanticGraph")
        image = os.environ.get("AE32C_SNAP_WORKER_IMAGE", "").strip()
        docker = shutil.which("docker")
        if not image:
            raise RuntimeError("snap_worker_image_not_configured")
        if not docker:
            raise RuntimeError("docker_runtime_not_available_for_snap_worker")

        self.semantic_graph = graph
        self._projection = make_projection(graph)
        self._index = dict(self._projection.node_to_index)
        self._edge_ids = {}
        self._fingerprint = graph_fingerprint(graph)
        self._request_counter = 0
        self._audit_cache = None
        self._metrics = {
            "native_adjacency_lookups": 0,
            "outgoing_native_edge_id_lookups": 0,
            "incoming_native_edge_id_lookups": 0,
            "native_edge_occurrences_read": 0,
        }
        self.worker_image = image
        self.worker_info: dict[str, Any] = {}
        command = [
            docker, "run", "--rm", "--pull=never", "-i",
            "--network=none", "--read-only",
            "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
            "--cap-drop=ALL", "--security-opt=no-new-privileges",
            "--pids-limit=64", "--memory=512m", "--cpus=1",
            "--user=65534:65534",
            "--env", "HOME=/tmp",
            "--env", "PYTHONDONTWRITEBYTECODE=1",
            "--env", "PYTHONNOUSERSITE=1",
            image,
        ]
        host_env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": tempfile.gettempdir(),
        }
        self._process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            bufsize=1,
            cwd=tempfile.gettempdir(),
            env=host_env,
            close_fds=True,
        )
        snapshot_nodes = [
            {
                "id": item["id"],
                "type": item["type"],
                "attributes": item["attributes"],
                "metadata": item["metadata"],
            }
            for item in self._projection.nodes
        ]
        snapshot_edges = [
            {
                "source": item["source"],
                "target": item["target"],
                "relation": item["relation"],
                "attributes": item["attributes"],
                "metadata": item["metadata"],
                "occurrence": item["occurrence"],
            }
            for item in self._projection.edges
        ]
        try:
            response = self._request(
                "init",
                nodes=snapshot_nodes,
                edges=snapshot_edges,
                graph_fingerprint=self._fingerprint,
            )
            if response.get("graph_fingerprint") != self._fingerprint:
                raise SNAPWorkerProtocolError("snap_worker_graph_fingerprint_mismatch")
            if response.get("node_count") != len(snapshot_nodes):
                raise SNAPWorkerProtocolError("snap_worker_node_count_mismatch")
            if response.get("edge_occurrence_count") != len(snapshot_edges):
                raise SNAPWorkerProtocolError("snap_worker_edge_count_mismatch")
            self.worker_info = response
            self.worker_info["container_image"] = image
            self.worker_info["container_image_id"] = os.environ.get(
                "AE32C_SNAP_WORKER_IMAGE_ID"
            )
            self.worker_info["container_policy"] = {
                "network": "none",
                "root_filesystem": "read_only",
                "capabilities": "all_dropped",
                "repository_mount": False,
                "provider_credentials_passed": False,
                "memory_limit": "512m",
                "cpu_limit": 1,
                "pid_limit": 64,
            }
        except Exception:
            self.close()
            raise

    def _request(self, operation: str, **payload: Any) -> dict[str, Any]:
        process = getattr(self, "_process", None)
        if process is None or process.poll() is not None:
            raise SNAPWorkerProtocolError("snap_worker_process_not_running")
        self._request_counter += 1
        request_id = str(self._request_counter)
        request = {
            "schema_version": self.PROTOCOL,
            "request_id": request_id,
            "operation": operation,
            "graph_fingerprint": self._fingerprint,
            **payload,
        }
        try:
            encoded = json.dumps(
                request, ensure_ascii=False, sort_keys=True,
                separators=(",", ":"), allow_nan=False,
            )
        except (TypeError, ValueError) as exc:
            raise SNAPWorkerProtocolError("snap_worker_request_not_json_serializable") from exc
        if len(encoded.encode("utf-8")) > 16 * 1024 * 1024:
            raise SNAPWorkerProtocolError("snap_worker_request_exceeds_size_limit")
        if process.stdin is None or process.stdout is None:
            raise SNAPWorkerProtocolError("snap_worker_protocol_stream_unavailable")
        process.stdin.write(encoded + "\n")
        process.stdin.flush()
        line = process.stdout.readline()
        if not line:
            raise SNAPWorkerProtocolError(
                f"snap_worker_terminated_without_response:{process.poll()}"
            )
        try:
            response = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SNAPWorkerProtocolError("snap_worker_response_not_valid_json") from exc
        if not isinstance(response, dict):
            raise SNAPWorkerProtocolError("snap_worker_response_not_object")
        if response.get("schema_version") != self.PROTOCOL:
            raise SNAPWorkerProtocolError("snap_worker_response_protocol_mismatch")
        if response.get("request_id") != request_id:
            raise SNAPWorkerProtocolError("snap_worker_response_id_mismatch")
        if response.get("status") != "ok":
            code = response.get("error_code", "unknown_worker_error")
            raise SNAPWorkerProtocolError(f"snap_worker_error:{code}")
        result = response.get("result")
        if not isinstance(result, dict):
            raise SNAPWorkerProtocolError("snap_worker_result_not_object")
        return result

    def _ensure_audit(self) -> dict[str, Any]:
        if self._audit_cache is None:
            report = self._request("audit")
            nodes, edges = report.get("nodes"), report.get("edges")
            if not isinstance(nodes, list) or not isinstance(edges, list):
                raise SNAPWorkerProtocolError("snap_worker_audit_payload_invalid")
            if len(nodes) != len(self._projection.nodes):
                raise SNAPWorkerProtocolError("snap_worker_audit_node_count_mismatch")
            if len(edges) != len(self._projection.edges):
                raise SNAPWorkerProtocolError("snap_worker_audit_edge_count_mismatch")
            node_map = {item.get("id"): item for item in nodes if isinstance(item, dict)}
            edge_map = {item.get("occurrence"): item for item in edges if isinstance(item, dict)}
            if len(node_map) != len(nodes) or len(edge_map) != len(edges):
                raise SNAPWorkerProtocolError("snap_worker_audit_identity_duplicate")
            audited_map = {
                item["occurrence"]: item["native_edge_id"] for item in edges
            }
            if set(audited_map) != set(range(len(self._projection.edges))):
                raise SNAPWorkerProtocolError("snap_worker_edge_identity_map_incomplete")
            self._edge_ids = audited_map
            self._audit_cache = {
                "nodes": deepcopy(nodes),
                "edges": deepcopy(edges),
            }
        return self._audit_cache

    def identity_mapping(self):
        self._ensure_audit()
        return super().identity_mapping()

    def iter_native_nodes(self):
        return iter(deepcopy(self._ensure_audit()["nodes"]))

    def iter_native_edges(self):
        return iter([
            {
                key: deepcopy(value)
                for key, value in item.items()
                if key != "native_edge_id"
            }
            for item in self._ensure_audit()["edges"]
        ])

    def iter_adjacent_edge_occurrences(
        self, node_id: str, direction: TraversalDirection
    ):
        if node_id not in self._index:
            raise KeyError(node_id)
        if isinstance(direction, str):
            direction = TraversalDirection(direction)
        if not isinstance(direction, TraversalDirection):
            raise ValueError("snap_adjacency_direction_invalid")
        result = self._request(
            "adjacency",
            node_id=node_id,
            direction=direction.value,
        )
        records = result.get("records")
        metrics = result.get("metrics")
        if not isinstance(records, list) or not isinstance(metrics, dict):
            raise SNAPWorkerProtocolError("snap_worker_adjacency_payload_invalid")
        self._metrics = dict(metrics)
        output = []
        seen = set()
        for item in records:
            if not isinstance(item, dict):
                raise SNAPWorkerProtocolError("snap_worker_edge_record_invalid")
            occurrence = item.get("occurrence")
            if type(occurrence) is not int or occurrence in seen:
                raise SNAPWorkerProtocolError("snap_worker_edge_occurrence_invalid_or_duplicate")
            seen.add(occurrence)
            output.append(NativeEdgeOccurrence(
                occurrence_id=occurrence,
                source_id=item.get("source"),
                target_id=item.get("target"),
                relation_type=item.get("relation"),
                attributes=deepcopy(item.get("attributes")),
                metadata=deepcopy(item.get("metadata")),
                backend_edge_ref=(
                    "snap-worker", item.get("native_edge_id"), occurrence,
                ),
            ))
        return tuple(output)

    def native_adjacency_report(self) -> dict:
        if self._process is None or self._process.poll() is not None:
            return dict(self._metrics)
        result = self._request("metrics")
        metrics = result.get("metrics")
        if isinstance(metrics, dict):
            self._metrics = dict(metrics)
        return dict(self._metrics)

    def capabilities(self):
        result = super().capabilities()
        result.update({
            "backend": "snap",
            "isolated_worker": True,
            "worker_python": self.worker_info.get("python_version"),
            "worker_snap_version": self.worker_info.get("snap_version"),
            "json_attributes_only": True,
            "attributes_stored_as_canonical_json": True,
            "native_adjacency": "TNEANetNodeI.GetOutEId/GetInEId",
        })
        return result

    def loss_report(self):
        result = super().loss_report()
        result["transformed"].append("attributes_encoded_as_canonical_json_strings")
        result["scope"] = (
            "isolated SNAP 6.0 worker; canonical JSON payloads; "
            "worker-local native edge IDs mapped to snapshot occurrence IDs"
        )
        return result

    def export(self):
        return {
            "backend": "snap",
            "transport": "versioned_json_lines",
            "worker_image": self.worker_image,
            "graph_fingerprint": self._fingerprint,
        }

    def backend_graph(self):
        return self.export()

    def close(self):
        process = getattr(self, "_process", None)
        if process is None:
            return
        self._process = None
        try:
            if process.poll() is None:
                try:
                    # The close frame is best-effort; the container is removed
                    # by Docker when stdin closes or the process exits.
                    request = {
                        "schema_version": self.PROTOCOL,
                        "request_id": "close",
                        "operation": "close",
                        "graph_fingerprint": self._fingerprint,
                    }
                    if process.stdin is not None:
                        process.stdin.write(json.dumps(request) + "\n")
                        process.stdin.flush()
                        if process.stdout is not None:
                            process.stdout.readline()
                except Exception:
                    pass
                if process.stdin is not None:
                    process.stdin.close()
                process.wait(timeout=5)
        except Exception:
            try:
                process.kill()
                process.wait(timeout=2)
            except Exception:
                pass

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
