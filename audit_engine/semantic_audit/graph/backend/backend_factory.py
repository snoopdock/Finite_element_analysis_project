"""
Semantic Graph Backend Factory.

Creates adapter instances from selected backend identifiers.
"""


from audit_engine.semantic_audit.graph.backend.networkx_adapter import (
    NetworkXAdapter,
)

from audit_engine.semantic_audit.graph.backend.scipy_adapter import (
    SciPyAdapter,
)


class BackendFactory:

    def __init__(self):
        self._adapters = {
            "networkx": NetworkXAdapter,
            "scipy": SciPyAdapter,
        }


    def register(self, name, adapter_class):
        self._adapters[name] = adapter_class


    def create(self, backend_name, graph):

        if backend_name not in self._adapters:
            raise ValueError(
                f"Unknown backend: {backend_name}"
            )

        adapter_class = self._adapters[backend_name]

        return adapter_class(graph)
