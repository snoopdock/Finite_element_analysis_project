"""
Semantic Graph Backend Factory with lazy backend imports.
"""


class BackendFactory:

    def __init__(self):
        self._backend_names = {
            "networkx",
            "scipy",
        }

    def register(self, name):
        self._backend_names.add(name)

    def available_backends(self):
        return sorted(self._backend_names)

    def create(self, backend_name, graph):

        if backend_name == "networkx":
            from audit_engine.semantic_audit.graph.backend.networkx_adapter import (
                NetworkXAdapter,
            )
            return NetworkXAdapter(graph)

        if backend_name == "scipy":
            from audit_engine.semantic_audit.graph.backend.scipy_adapter import (
                SciPyAdapter,
            )
            return SciPyAdapter(graph)

        raise ValueError(
            f"Unknown backend: {backend_name}"
        )
