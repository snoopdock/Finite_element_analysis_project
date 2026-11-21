"""Graph backend capabilities and optional dependency availability."""

import os
import shutil

from audit_engine.semantic_audit.graph.backend.optional_backend_support import backend_available


class BackendCapabilityRegistry:
    def __init__(self):
        self._backends = {}

    def register(self, name, adapter, capabilities):
        self._backends[name] = {"adapter": adapter, "capabilities": dict(capabilities)}

    def get(self, name):
        return self._backends[name]

    def list_backends(self):
        return list(self._backends.keys())

    def describe(self):
        return {name: dict(item["capabilities"]) for name, item in self._backends.items()}


def _acceptance_state(backend_name, adjacency_implementation, *, worker_configured=False):
    """Separate implementation/discoverability from conformance and approval."""
    return {
        "implementation": "present",
        "module_discoverable": backend_available(backend_name),
        "worker_configured": bool(worker_configured),
        "api_compatibility": "not_checked",
        "structural_conformance": "not_run",
        "native_adjacency_conformance": "not_run",
        "native_adjacency_implementation": adjacency_implementation,
        "repository_conformance": "not_run",
        "production_approval": False,
    }


def create_default_registry():
    registry = BackendCapabilityRegistry()
    registry.register("networkx", "NetworkXAdapter", {
        "acceptance_state": _acceptance_state("networkx", "implemented_unvalidated"),
        "lossless": True, "metadata": True, "multiedges": True,
        "directed": True, "semantic_traversal": True,
        "available": backend_available("networkx"),
    })
    registry.register("scipy", "SciPyAdapter", {
        "acceptance_state": _acceptance_state("scipy", "implemented_unvalidated"),
        # CSR is a hybrid backend: the matrix indexes connectivity while
        # exact typed edge occurrences and metadata are preserved separately.
        "lossless": False, "sparse_matrix": True, "metadata": False,
        "relation_side_channel": True, "directed": True, "multiedges": False,
        "semantic_traversal": True, "side_channel_preservation": True,
        "available": backend_available("scipy"),
    })

    snap_worker_configured = (
        bool(os.environ.get("AE32C_SNAP_WORKER_IMAGE", "").strip())
        and shutil.which("docker") is not None
    )
    for name, klass in (
        ("igraph", "IGraphAdapter"),
        ("graph-tool", "GraphToolAdapter"),
        ("snap", "SNAPAdapter"),
    ):
        native_adjacency = (
            name in {"igraph", "graph-tool"}
            or (name == "snap" and snap_worker_configured)
        )
        available = (
            snap_worker_configured or backend_available("snap")
            if name == "snap" else backend_available(name)
        )
        registry.register(name, klass, {
            "acceptance_state": _acceptance_state(
                name,
                "implemented_unvalidated" if native_adjacency else "not_implemented",
                worker_configured=(name == "snap" and snap_worker_configured),
            ),
            "lossless": True, "metadata": True, "multiedges": True,
            "directed": True, "semantic_traversal": True,
            "available": available,
            "optional": True,
            "json_attributes_only": name == "snap",
        })
    return registry
