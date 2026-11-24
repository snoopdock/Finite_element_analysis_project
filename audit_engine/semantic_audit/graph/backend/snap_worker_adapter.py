"""Python 3.11 proxy for the isolated CPython 3.9 SNAP worker.

The SNAP native module is never imported into the project interpreter. A
minimal Docker container receives only a JSON graph snapshot and bounded
adjacency requests. The container has no network, no repository mount, a
read-only root filesystem and no Linux capabilities.
"""
from __future__ import annotations

import json
import math
import os
import queue
import shutil
import subprocess
import tempfile
import threading
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


class SNAPWorkerTimeoutError(SNAPWorkerProtocolError):
    """A worker request exceeded its configured wall-clock deadline."""


class SNAPWorkerAdapter(NativeAdapterMixin, SemanticGraphAdapter):
    """Native TNEANet adapter whose implementation runs only in the worker."""

    backend_name = "snap"
    is_isolated_worker = True
    PROTOCOL = "ae32c/snap-worker/v1"
    REQUEST_TIMEOUT_ENV = "AE32C_SNAP_WORKER_REQUEST_TIMEOUT_SECONDS"
    DEFAULT_REQUEST_TIMEOUT_SECONDS = 120.0
    MAX_REQUEST_TIMEOUT_SECONDS = 600.0
    CLOSE_REQUEST_TIMEOUT_SECONDS = 5.0
    PROCESS_TERMINATE_TIMEOUT_SECONDS = 1.0

    def __init__(self, graph: SemanticGraph):
        if not isinstance(graph, SemanticGraph):
            raise TypeError("SNAPWorkerAdapter requires a SemanticGraph")
        image = os.environ.get("AE32C_SNAP_WORKER_IMAGE", "").strip()
        raw_timeout = os.environ.get(
            self.REQUEST_TIMEOUT_ENV,
            str(self.DEFAULT_REQUEST_TIMEOUT_SECONDS),
        ).strip()
        try:
            request_timeout = float(raw_timeout)
        except (TypeError, ValueError) as exc:
            raise ValueError("snap_worker_request_timeout_invalid") from exc
        if (
            not math.isfinite(request_timeout)
            or request_timeout <= 0
            or request_timeout > self.MAX_REQUEST_TIMEOUT_SECONDS
        ):
            raise ValueError("snap_worker_request_timeout_out_of_range")

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
        self._request_timeout_seconds = request_timeout
        self._request_lock = threading.RLock()
        self._audit_cache = None
        self._metrics = {
            "native_adjacency_lookups": 0,
            "outgoing_native_edge_id_lookups": 0,
            "incoming_native_edge_id_lookups": 0,
            "native_edge_occurrences_read": 0,
        }
        self.worker_image = image
        self.worker_info: dict[str, Any] = {}
        host_env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": "/nonexistent",
        }
        self._docker_executable = docker
        self._docker_env = host_env
        self._container_state_dir = tempfile.mkdtemp(prefix="ae32c-snap-worker-")
        self._container_id_file = os.path.join(
            self._container_state_dir, "container-id"
        )
        command = [
            docker, "run", "--rm", "--pull=never",
            "--cidfile", self._container_id_file,
            "--init", "-i",
            "--network=none", "--ipc=none", "--read-only",
            "--cap-drop=ALL", "--security-opt=no-new-privileges",
            "--pids-limit=64", "--memory=512m", "--cpus=1",
            "--user=65534:65534",
            "--env", "HOME=/tmp",
            "--env", "PYTHONDONTWRITEBYTECODE=1",
            "--env", "PYTHONNOUSERSITE=1",
            image,
        ]
        try:
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
        except Exception:
            shutil.rmtree(self._container_state_dir, ignore_errors=True)
            raise
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
            self.worker_info["request_timeout_seconds"] = self._request_timeout_seconds
            self.worker_info["request_timeout_enforced"] = True
            self.worker_info["container_image"] = image
            self.worker_info["container_image_id"] = os.environ.get(
                "AE32C_SNAP_WORKER_IMAGE_ID"
            )
            self.worker_info["container_policy"] = {
                "network": "none",
                "ipc": "none",
                "root_filesystem": "read_only",
                "writable_mounts": [],
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

    def _force_remove_container(self) -> bool:
        """Force-remove the exact worker container recorded by Docker."""
        cidfile = getattr(self, "_container_id_file", None)
        if not cidfile or not os.path.isfile(cidfile):
            return False
        try:
            with open(cidfile, "r", encoding="ascii") as handle:
                container_id = handle.read().strip()
        except OSError:
            return False
        if not container_id:
            return False

        try:
            result = subprocess.run(
                [self._docker_executable, "rm", "--force", container_id],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                cwd=tempfile.gettempdir(),
                env=self._docker_env,
                check=False,
                timeout=2.0,
            )
            return result.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            return False

    def _stop_process(
        self,
        process: subprocess.Popen,
        exchange_thread: threading.Thread | None = None,
    ) -> None:
        """Stop the exact Docker worker, then release pipes with bounded waits."""
        if getattr(self, "_process", None) is process:
            self._process = None

        if process.poll() is None:
            # Do not rely solely on SIGTERM to the docker CLI: PID 1 inside a
            # container has special signal handling. Force-remove the known
            # container first, which makes Docker send SIGKILL to its main
            # process and remove it even if the worker is not responding.
            self._force_remove_container()
            if process.poll() is None:
                try:
                    process.terminate()
                except (OSError, ProcessLookupError):
                    pass
            try:
                process.wait(timeout=self.PROCESS_TERMINATE_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                try:
                    process.kill()
                except (OSError, ProcessLookupError):
                    pass
                try:
                    process.wait(timeout=self.PROCESS_TERMINATE_TIMEOUT_SECONDS)
                except Exception:
                    pass
            except Exception:
                try:
                    process.kill()
                    process.wait(timeout=self.PROCESS_TERMINATE_TIMEOUT_SECONDS)
                except Exception:
                    pass

        # Process exit makes a blocked pipe read/write observable as EOF or
        # BrokenPipe. Close streams only after the child has been stopped.
        for stream in (process.stdin, process.stdout):
            if stream is not None:
                try:
                    stream.close()
                except Exception:
                    pass
        if exchange_thread is not None and exchange_thread.is_alive():
            exchange_thread.join(timeout=self.PROCESS_TERMINATE_TIMEOUT_SECONDS)

        state_dir = getattr(self, "_container_state_dir", None)
        if state_dir:
            shutil.rmtree(state_dir, ignore_errors=True)
            self._container_state_dir = None

    def _request(
        self,
        operation: str,
        *,
        timeout_seconds: float | None = None,
        **payload: Any,
    ) -> dict[str, Any]:
        """Perform one serialized JSON-lines RPC under a wall-clock deadline.

        Blocking pipe I/O runs in a daemon thread so the caller can terminate
        the worker when either stdin flush or stdout response stalls. A timed
        out worker is discarded; the adapter never reuses a desynchronized
        protocol stream.
        """
        with self._request_lock:
            process = getattr(self, "_process", None)
            if process is None or process.poll() is not None:
                raise SNAPWorkerProtocolError("snap_worker_process_not_running")

            effective_timeout = (
                self._request_timeout_seconds
                if timeout_seconds is None
                else float(timeout_seconds)
            )
            if (
                not math.isfinite(effective_timeout)
                or effective_timeout <= 0
                or effective_timeout > self.MAX_REQUEST_TIMEOUT_SECONDS
            ):
                raise ValueError("snap_worker_request_timeout_out_of_range")

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
                raise SNAPWorkerProtocolError(
                    "snap_worker_request_not_json_serializable"
                ) from exc
            if len(encoded.encode("utf-8")) > 16 * 1024 * 1024:
                raise SNAPWorkerProtocolError(
                    "snap_worker_request_exceeds_size_limit"
                )
            if process.stdin is None or process.stdout is None:
                raise SNAPWorkerProtocolError(
                    "snap_worker_protocol_stream_unavailable"
                )

            outcome: queue.Queue[tuple[str, Any]] = queue.Queue(maxsize=1)

            def exchange() -> None:
                try:
                    process.stdin.write(encoded + "\n")
                    process.stdin.flush()
                    line = process.stdout.readline()
                    outcome.put(("response", line))
                except BaseException as exc:
                    outcome.put(("error", exc))

            exchange_thread = threading.Thread(
                target=exchange,
                name=f"snap-worker-{operation}-{request_id}",
                daemon=True,
            )
            exchange_thread.start()
            try:
                kind, value = outcome.get(timeout=effective_timeout)
            except queue.Empty as exc:
                self._stop_process(process, exchange_thread)
                raise SNAPWorkerTimeoutError(
                    f"snap_worker_request_timeout:{operation}:"
                    f"{effective_timeout:g}s"
                ) from exc

            if kind == "error":
                self._stop_process(process, exchange_thread)
                raise SNAPWorkerProtocolError(
                    f"snap_worker_request_io_failed:{operation}"
                ) from value

            line = value
            if not line:
                self._stop_process(process, exchange_thread)
                raise SNAPWorkerProtocolError(
                    f"snap_worker_terminated_without_response:{process.poll()}"
                )
            try:
                response = json.loads(line)
            except json.JSONDecodeError as exc:
                self._stop_process(process, exchange_thread)
                raise SNAPWorkerProtocolError(
                    "snap_worker_response_not_valid_json"
                ) from exc
            if not isinstance(response, dict):
                self._stop_process(process, exchange_thread)
                raise SNAPWorkerProtocolError("snap_worker_response_not_object")
            if response.get("schema_version") != self.PROTOCOL:
                self._stop_process(process, exchange_thread)
                raise SNAPWorkerProtocolError(
                    "snap_worker_response_protocol_mismatch"
                )
            if response.get("request_id") != request_id:
                self._stop_process(process, exchange_thread)
                raise SNAPWorkerProtocolError("snap_worker_response_id_mismatch")
            if response.get("status") != "ok":
                code = response.get("error_code", "unknown_worker_error")
                raise SNAPWorkerProtocolError(f"snap_worker_error:{code}")
            result = response.get("result")
            if not isinstance(result, dict):
                self._stop_process(process, exchange_thread)
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
            "request_timeout_seconds": self._request_timeout_seconds,
            "request_timeout_enforced": True,
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
            "request_timeout_seconds": self._request_timeout_seconds,
        }

    def backend_graph(self):
        return self.export()

    def close(self):
        lock = getattr(self, "_request_lock", None)
        if lock is None:
            process = getattr(self, "_process", None)
            if process is not None:
                self._stop_process(process)
            return

        with lock:
            process = getattr(self, "_process", None)
            if process is None:
                return
            try:
                if process.poll() is None:
                    try:
                        # The close RPC uses a short deadline independent of
                        # the larger initialization/adjacency request budget.
                        self._request(
                            "close",
                            timeout_seconds=min(
                                self.CLOSE_REQUEST_TIMEOUT_SECONDS,
                                self._request_timeout_seconds,
                            ),
                        )
                    except SNAPWorkerProtocolError:
                        # _request has already stopped the worker after an
                        # RPC timeout or protocol/pipe failure.
                        pass

                if getattr(self, "_process", None) is process and process.poll() is None:
                    if process.stdin is not None:
                        try:
                            process.stdin.close()
                        except Exception:
                            pass
                    try:
                        process.wait(timeout=self.CLOSE_REQUEST_TIMEOUT_SECONDS)
                    except subprocess.TimeoutExpired:
                        self._stop_process(process)
                    except Exception:
                        self._stop_process(process)

                self._stop_process(process)
            finally:
                if getattr(self, "_process", None) is process:
                    self._process = None

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
